# Testing the camera flow on a real phone

This tests the PWA capture loop end to end:

```
snap → review (retake / use) → 5 photos per batch → upload → Finished
```

The phone opens the app from this Mac over the home Wi-Fi. It uses plain
HTTP: no HTTPS, no service worker. Uploaded photos land in
`data/batches/<batch_id>/` on the Mac.

## 1. One-time setup (on the Mac, from the repo root)

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
```

## 2. Find the Mac's address on the Wi-Fi

```bash
ipconfig getifaddr en0
```

It prints something like `192.168.1.16`. If it prints nothing, the Mac is on a
different interface; try `ipconfig getifaddr en1`. Below, `MAC_IP` means this
address.

## 3. Start both servers (two terminals, both from the repo root)

Backend, port 8000:

```bash
.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

App, port 8080:

```bash
python3 -m http.server 8080 --bind 0.0.0.0 --directory app
```

- `--host 0.0.0.0` matters. Without it, uvicorn only listens on localhost and
  the phone can't reach it.
- If macOS asks whether Python may accept incoming network connections, click
  **Allow**.

## 4. Check from the Mac before picking up the phone

```bash
curl http://MAC_IP:8000/health
```

Expected: `{"status":"ok","service":"binbuild","version":"0.1.0"}`.

Then open `http://MAC_IP:8080` in a desktop browser. The line under the yellow
header should say **Backend: connected (http://MAC_IP:8000)**.

## 5. Open the app on the phone

- Put the phone on the **same Wi-Fi** as the Mac. A guest network usually
  blocks devices from seeing each other.
- Open **`http://MAC_IP:8080`** in Safari on iPhone or Chrome on Android. Type
  `http://` explicitly.
- The app finds the backend by itself: it uses the page's own host on port
  8000.
  - To point it somewhere else, edit `BACKEND_URL` at the top of
    `app/app.js`.
- Check the line under the header:
  - **green dot, "Backend: connected"**: good to go;
  - **red dot, "not reachable"**: go back to steps 3–4.

## 6. The 5-photo test

1. Scatter a handful of pieces on a table in one flat layer.
2. The card says **Batch 1 · photo 1 of 5: top view**. Tap **📷 Take photo**:
   the rear camera opens. Take the photo and accept it in the camera.
3. The **review** screen shows the photo full width.
   - Tap **↺ Retake** once to check that it reopens the camera and the new
     shot replaces the old one.
   - Then tap **✓ Use photo**.
4. Back on the card, the top slot shows a thumbnail. The title moves on to
   **photo 2 of 5: side 1 (front)**.
   - Take front, right, back and left the same way, using **✓ Use photo**
     each time.
5. After the 5th photo, the title reads **Batch 1 · all 5 photos taken** and
   **⬆ Upload batch (5/5)** turns on.
   - Optional: tap **✕** on one thumbnail. That slot opens again; retake it.
6. Tap **⬆ Upload batch**.
   - A progress bar and percentage appear.
   - **Pass:** a green ✓ line reads "Batch 1 uploaded: 5 photos saved as
     `<batch_id>`", the slots clear, and the title becomes **Batch 2 · photo 1
     of 5**.
7. **Failure check:** stop the backend (Ctrl-C in its terminal), take another
   5 photos, and tap Upload.
   - **Pass:** a red ✗ line reads "Upload failed: couldn't reach the backend
     at http://MAC_IP:8000 …", and the 5 photos stay.
   - Restart the backend, tap **Re-check** (the dot turns green), then tap
     Upload again. It should succeed as batch 2.
8. Tap **Finished — show my batches**.
   - **Pass:** "2 batches (10 photos) uploaded this session", with both batch
     ids listed.

## 7. Confirm on the Mac

```bash
ls data/batches/
ls -la data/batches/<batch_id>/
cat data/batches/<batch_id>/batch.json
```

Each batch folder holds:
- the 5 photos, `1-top.jpg`, `2-front.jpg`, `3-right.jpg`, `4-back.jpg` and
  `5-left.jpg`, byte-for-byte what the phone sent;
- `batch.json`, listing view, file, size and the phone's original filename.

Open a photo to check it is the full-resolution camera image.

## The API, for curl testing without a phone

`POST /api/inventory/batch`:
- **Request:** multipart form with exactly 5 `photos` files, in the order top,
  front, right, back, left.
- **Success:** `201`, with
  `{"batch_id": "...", "photos_saved": 5, "photos": [...]}`.
- **Errors:**
  - `422`: not exactly 5 photos, a non-image, or an empty file;
  - `413`: a photo over 30 MB.
  - A failed upload leaves nothing on disk.

```bash
curl -F photos=@top.jpg -F photos=@front.jpg -F photos=@right.jpg \
     -F photos=@back.jpg -F photos=@left.jpg \
     http://MAC_IP:8000/api/inventory/batch
```

## Known limits

- **On low-memory Android phones, Chrome may reload the page while the
  camera app is open.** That loses the photos taken so far in the current
  batch, because the app keeps them in memory only. If you see the batch reset
  after taking a photo, note the phone model.
- **No HTTPS, so no service worker and no "Add to Home Screen" install over
  the LAN.** That is expected. The app logs "no service worker (not a secure
  context)" and works normally.
- **Photos aren't identified yet.** Review and confirm of the pieces found,
  and the inventory database, are the next spike.

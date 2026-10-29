# Testing the camera flow on a real phone

This tests the PWA end to end:

```
snap → review (retake / use) → 5 photos per batch → upload + photo check → Identify
     → Check the pieces (fix / remove / add) → Add to my inventory → What can I build? → booklet
```

Sections 1–7 cover capture and upload; section 8 covers checking the pieces
and building.

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
   - **Pass:** every batch on the backend is listed, newest first, with its
     state: "not identified yet", "N pieces waiting for you to check" or
     "N pieces in your inventory". Reloading the page and tapping Finished
     again shows the same list.

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

## 8. Check the pieces, add them, build

Needs the Baseten key in `.env` (Identify calls Muse Spark, about a minute
for 50 pieces).

1. With a batch uploaded and all 5 photos clear, tap **Identify pieces**.
   - **Pass:** the **Check the pieces** screen opens: the top photo with a
     dot on every piece, a line like "50 pieces · 6 plain bricks BrickGPT can
     use", and the pieces grouped by kind ("4× lime 1x1 round plate").
2. Tap a row.
   - **Pass:** its pieces get yellow rings on the photo, the others fade, and
     the caption under the photo names them. The photo stays at the top while
     the list scrolls. Tap a dot: that one piece gets a big ring.
3. Find a row Spark got wrong and tap **✎ Fix all N**.
   - **Pass:** the form shows what it says now. Change shape, size, colour or
     the **Plain** box: the line under it says whether BrickGPT can build with
     it. **Save**: the row changes and is marked "fixed".
   - Only some of a row wrong? **One by one ▾**, then **✎ Fix** or **✕ Remove**
     on that piece.
4. **✕ Remove** something that isn't a piece (or was counted twice).
   - **Pass:** it moves to "Removed: not added to your inventory", and the
     count drops. **↩ Put back** undoes it.
5. **＋ Add a piece Spark missed**, with How many.
   - **Pass:** a row "added by you" appears and the count goes up.
6. Tap **✓ Add N pieces to my inventory**.
   - **Pass:** "✓ Added to your inventory" with the new inventory total, and
     buttons for **What can I build?**, **Scan the next handful** and **Undo**.
7. Tap **Undo**.
   - **Pass:** "Took N pieces out of your inventory", and the batch is open
     to check again. Add it again. (Only the last batch added can be undone:
     an older one says so.)
8. Tap **What can I build?**, then **📖 Make the booklet** on a build that
   fits, then **Open the booklet**.
   - **Pass:** a page with the finished model, the pieces to find, and one
     picture per step. Builds that don't fit say what is missing.

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
- **The review screen points at pieces, it doesn't outline them.** Each dot is
  Spark's centre point for a piece; per-piece outlines and close-up crops
  need SAM 3.1. Pieces added by hand have no dot.
- **Booklets open from the backend** (a link to `http://MAC_IP:8000/...`), in
  a new browser tab.

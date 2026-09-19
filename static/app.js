// Demo photos use plain GET navigation, so every demo pile has a permalink.
// Uploaded photos are shrunk here in the browser, kept in memory, and POSTed
// with the options on every render; the server stores nothing.

const MAX_EDGE = 1600; // longest edge, in pixels, of each photo sent to the server
const JPEG_QUALITY = 0.9;

const form = document.getElementById("controls");
const applyButton = document.getElementById("apply");
const upload = document.getElementById("upload");
const useDemo = document.getElementById("use-demo");
const photoStatus = document.getElementById("photo-status");
const message = document.getElementById("message");
const pile = document.getElementById("pile");
const download = document.getElementById("download");
const permalink = document.getElementById("permalink");
const maxFiles = Number(form.dataset.maxFiles);

let uploads = null; // shrunk JPEG blobs, or null when showing the demo photos
let seed = Number(applyButton.value);
let pileUrl = null; // object URL of the current uploaded-photo render
let latestRequest = 0; // so a slow earlier render can't overwrite a newer one

// Changing an option re-renders the same layout straight away.
// (The slider fires "change" on release, so dragging doesn't render every step.)
form.addEventListener("change", (event) => {
  if (event.target !== upload) form.requestSubmit(applyButton);
});

form.addEventListener("submit", (event) => {
  if (!uploads) return; // demo photos: normal navigation
  event.preventDefault();
  if (event.submitter !== applyButton) seed = randomSeed();
  renderUploads();
});

upload.addEventListener("change", async () => {
  let files = [...upload.files];
  upload.value = ""; // so choosing the same files again still fires "change"
  if (!files.length) return;

  const notes = [];
  if (files.length > maxFiles) {
    notes.push(`Only the first ${maxFiles} photos were used.`);
    files = files.slice(0, maxFiles);
  }
  showMessage(`Preparing ${files.length} photo${files.length === 1 ? "" : "s"}…`);
  const results = await Promise.all(files.map((f) => shrink(f).catch(() => null)));
  const unreadable = files.filter((_, i) => !results[i]).map((f) => f.name);
  if (unreadable.length) {
    notes.push(`Couldn't read ${unreadable.join(", ")}. Try JPEG or PNG.`);
  }

  const blobs = results.filter(Boolean);
  if (!blobs.length) {
    showMessage(notes.join(" "), true);
    return;
  }
  uploads = blobs;
  seed = randomSeed();
  photoStatus.textContent = `${blobs.length} of your photo${blobs.length === 1 ? "" : "s"}`;
  useDemo.hidden = false;
  permalink.hidden = true; // uploaded photos aren't stored, so there's nothing to link to
  await renderUploads();
  if (notes.length) showMessage(notes.join(" "), true);
});

useDemo.addEventListener("click", () => {
  uploads = null;
  form.requestSubmit(applyButton); // back to a normal demo-photo page, same options
});

async function renderUploads() {
  const request = ++latestRequest;
  const data = new FormData(form);
  data.set("seed", seed);
  uploads.forEach((blob, i) => data.append("photos", blob, `photo-${i + 1}.jpg`));

  pile.classList.add("busy");
  showMessage("Rendering…");
  try {
    const response = await fetch(form.dataset.uploadUrl, { method: "POST", body: data });
    if (request !== latestRequest) return;
    if (!response.ok) {
      showMessage(await response.text(), true);
      return;
    }
    const blob = await response.blob();
    if (request !== latestRequest) return;
    if (pileUrl) URL.revokeObjectURL(pileUrl);
    pileUrl = URL.createObjectURL(blob);
    pile.src = pileUrl;
    download.href = pileUrl;
    download.download = `photo-pile-${seed}.jpg`;
    applyButton.value = seed;
    hideMessage();
  } catch {
    if (request === latestRequest) showMessage("Couldn't reach the server. Please try again.", true);
  } finally {
    if (request === latestRequest) pile.classList.remove("busy");
  }
}

// Decode a photo and re-encode it as a JPEG no bigger than MAX_EDGE. Decoding
// through an <img> applies the camera's EXIF rotation and lets the browser read
// any format it supports (Safari can read iPhone HEIC files, for example).
async function shrink(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image();
    img.src = url;
    await img.decode();
    const scale = Math.min(1, MAX_EDGE / Math.max(img.naturalWidth, img.naturalHeight));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.naturalWidth * scale);
    canvas.height = Math.round(img.naturalHeight * scale);
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#fff"; // transparent PNG areas become white, not black
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((resolve, reject) =>
      canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("encode failed"))), "image/jpeg", JPEG_QUALITY),
    );
  } finally {
    URL.revokeObjectURL(url);
  }
}

function randomSeed() {
  return Math.floor(Math.random() * 1_000_000);
}

function showMessage(text, isError = false) {
  message.textContent = text;
  message.classList.toggle("error", isError);
  message.hidden = false;
}

function hideMessage() {
  message.hidden = true;
}

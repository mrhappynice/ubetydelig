Muffled (“wah-wah-wah”) output with Kokoro via Transformers.js usually means that the raw audio bytes aren’t being decoded or resampled correctly before playback. Below are a few common culprits and how to check/fix them:

---

## 1. Verify you’re requesting a high-quality codec/sample-rate

By default, Kokoro may return a low-bitrate or resampled stream if you don’t explicitly ask for a higher-quality format. In Transformers.js you can pass a `codec` (and, in some versions, a `sampleRate`) option when calling the TTS method. For example:

```js
// Example with Transformers.js v3+ API
import { pipeline, setWasmPath } from "@xenova/transformers";

// (Assuming you already initialized the WebGPU backend elsewhere)
const tts = await pipeline("text-to-speech", "Xenova/kokoro-tts", { 
  // force WAV (uncompressed) instead of low-bitrate Ogg/Vorbis etc.
  codec: "wav",
  // if supported, explicitly ask for 24000 Hz (Kokoro supports 24 kHz)
  // (some versions of Transformers.js let you pass sampleRate)
  sampleRate: 24000,
});

// Synthesize:
const { data } = await tts(text, { speaker: "alloy", codec: "wav" });
// `data` is now an ArrayBuffer (raw WAV).
```

1. **“codec: 'wav'”** ensures you’re getting uncompressed PCM instead of a highly compressed format.
2. **“sampleRate: 24000”** (if your version supports it) tells Kokoro to return a 24 kHz WAV. Kokoro’s native output is usually 24 kHz; if you get 8 kHz or 16 kHz, it will sound muffled.

If you don’t explicitly request `codec: "wav"`, Transformers.js might be returning a low-bitrate Ogg/Vorbis (e.g., 8 kHz) that, once decoded, sounds very muddy. 

> **→ Action:** Double-check your call to `tts()` (or `model.speech()`) and add `codec: "wav"` (and `sampleRate: 24000` if available).

---

## 2. Ensure you decode the raw bytes with the correct sample rate

Even if Kokoro gives you a 24 kHz WAV, the browser’s `AudioContext` may assume a different sample rate (often 44.1 kHz or 48 kHz). If you simply pass the raw bytes to `decodeAudioData` without specifying anything, Chrome/Firefox will try to read the WAV header and use its internal rate—but mismatches can slip through if your WAV header is malformed or if you accidentally chop off bytes.

A solid pattern is:

```js
// 1) Create a single, global AudioContext:
const audioContext = new AudioContext(); // Usually defaults to 48 kHz on Windows

// 2) After you get `ArrayBuffer` back from model:
const arrayBuffer = data; // e.g. response.data from Transformers.js

// 3) Decode it:
const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

// 4) Play it:
const source = audioContext.createBufferSource();
source.buffer = audioBuffer;
source.connect(audioContext.destination);
source.start();
```

If `decodeAudioData` fails or silently yields a 8 kHz‐only buffer but playback is forced at 48 kHz, it will sound “lo-fi.” To check:

1. **Log the decoded buffer’s `sampleRate`:**

   ```js
   console.log("decoded sampleRate =", audioBuffer.sampleRate);
   console.log("decoded length (frames) =", audioBuffer.length);
   ```

   * If you requested 24 kHz but see 8000 Hz or 16000 Hz, you know Kokoro returned a low-sample-rate stream.
   * If you requested 24 kHz and you see 24000 Hz, that’s good. If you see 48000 Hz, your browser might have re-sampled it under the hood (that usually still sounds fine).

2. **Inspect the WAV header manually** (if you suspect it’s truncated). In code, you can do a quick char check:

   ```js
   const dv = new DataView(arrayBuffer);
   // "RIFF" should be bytes 0–3
   console.log(
     String.fromCharCode(
       dv.getUint8(0),
       dv.getUint8(1),
       dv.getUint8(2),
       dv.getUint8(3)
     )
   ); // should print "RIFF"
   ```

   If you don’t get “RIFF” or “WAVEfmt ” near the start, the response may be cut off or corrupted.

> **→ Action:** After `decodeAudioData`, log out `audioBuffer.sampleRate` and confirm it’s 24000 Hz (or at least ≥16000 Hz). If it’s 8000 Hz, that’s why it’s muffled.

---

## 3. Double-check that WebGPU inference isn’t dropping/altering the audio tensor

Although WebGPU primarily affects the **model inference** (text→mel spectrogram) stage, if the final vocoder or post-processing step runs on GPU and you have a bug in how you transfer the buffer back to CPU, you could corrupt audio. For example:

* If you use `tf.tensor()` or `ort.Tensor()` improperly, you might end up with quantized/int8 data instead of float32 PCM.
* If you do a manual `fetch()` on a `data.uri` and forget to call `.arrayBuffer()` (or convert a Base64 string incorrectly), you can end up with half-bytes.

**How to check:**

1. Before playing, create a `<audio>` tag in HTML and set its `src` directly to a `Blob` of the arrayBuffer:

   ```js
   const wavBlob = new Blob([arrayBuffer], { type: "audio/wav" });
   const url = URL.createObjectURL(wavBlob);
   document.querySelector("#debugAudio").src = url;
   ```

   If playing that `<audio>` still sounds muffled, the problem is upstream (the bytes themselves). If it sounds clear in the `<audio>` tag, but sounds bad when you do the `AudioContext.decodeAudioData→BufferSource` path, then the issue is in your decode/play logic (e.g. sample-rate mismatch).

2. If you’re able to download the WAV (e.g., via a link) and load it into Audacity or VLC, does it still sound muffled? That’ll tell you if the problem is during TTS or during your browser’s playback.

> **→ Action:** Quick debug: turn the raw `ArrayBuffer` into a Blob and play it in a plain `<audio>` element. If that is clear, the issue is in your JavaScript decode/play; if it’s still muffled, the issue is Kokoro or the way you requested the codec.

---

## 4. Make sure you’re using the correct Transformers.js version (& backend flags)

Different versions of Transformers.js changed how they expose the TTS pipeline and how they handle codecs. If you’re on an older version (v2.x), it might default to 8 kHz Opus. In v3.x+, you usually have to explicitly pass `{ codec: "wav" }`. Also:

* **If you’re forcing WebGPU** but your GPU or driver doesn’t fully support certain compute shapes, the vocoder step might be falling back to a low-bit depth runtime. Try switching to the Wasm backend just to compare:

  ```js
  // temporarily disable WebGPU:
  import { setWasmPath, setBackend } from "@xenova/transformers";
  await setBackend("wasm"); 
  // then re-run your pipeline and check if audio still sounds muffled
  ```

  If the Wasm backend outputs clean audio, that indicates something in the WebGPU path is dropping precision.

> **→ Action:** Try toggling the backend: if you currently do
>
> ```js
> import { setWasmPath, setWebGPUBackend } from "@xenova/transformers";
> await setWebGPUBackend();
> ```
>
> switch to
>
> ```js
> await setBackend("wasm");
> ```
>
> and see if the audio is still muffled. If the wasm path sounds fine, you know the GPU-based vocoder path needs further attention.

---

## 5. Example end-to-end snippet

Below is a minimal example that requests a 24 kHz WAV from Kokoro and plays it back. Drop this into a fresh HTML/JS sandbox (e.g. CodeSandbox or a local static file) and see if it still sounds muffled. If this is fine, compare line-by-line against your own code to spot the discrepancy.

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Kokoro TTS Debug</title>
</head>
<body>
  <button id="speakBtn">Speak</button>
  <audio id="debugAudio" controls></audio>

  <script type="module">
    import { pipeline, setWasmPath, setBackend } from "https://cdn.jsdelivr.net/npm/@xenova/transformers@3/dist/transformers.js";

    // 1) (Optional) If you have a local `.wasm` file, do:
    //    setWasmPath("/path/to/transformers.wasm");
    // 2) Force Wasm or WebGPU backend:
    //    await setBackend("webgpu"); // or "wasm"
    await setBackend("webgpu"); // or try "wasm"

    const ttsPipeline = await pipeline("text-to-speech", "Xenova/kokoro-tts", {
      // ensure uncompressed, 24 kHz output
      codec: "wav",
      sampleRate: 24000,
    });

    document.getElementById("speakBtn").addEventListener("click", async () => {
      const text = "Hello, this is a debug test. If you hear muffled sound, something is off.";
      const { data } = await ttsPipeline(text, {
        speaker: "alloy",
        codec: "wav",
        sampleRate: 24000,
      });

      // A) Quick-and-dirty playback via <audio> tag:
      const wavBlob = new Blob([data], { type: "audio/wav" });
      const url = URL.createObjectURL(wavBlob);
      document.getElementById("debugAudio").src = url;

      // B) Also try AudioContext.decodeAudioData path:
      const audioContext = new AudioContext();
      const decoded = await audioContext.decodeAudioData(data);
      console.log("Decoded sampleRate:", decoded.sampleRate);
      const src = audioContext.createBufferSource();
      src.buffer = decoded;
      src.connect(audioContext.destination);
      src.start();
    });
  </script>
</body>
</html>
```

1. Click “Speak.”
2. Listen to the `<audio>` element. Is it clear?
3. Then listen to the `AudioContext` playback. Check your console for `decoded.sampleRate`.

If both sound good, your environment/driver is fine and your original code likely forgot to set `codec: "wav"` or mismatched sample rates.

---

## 6. If it’s still muffled after the above…

1. **Check your GPU drivers:**

   * On Windows 10 with an RX 6600, make sure you have the latest AMD Adrenalin drivers. Out-of-date drivers can cause precision-loss in WebGPU compute shaders.

2. **Compare file sizes:**

   * A 24 kHz WAV of a 3-second utterance is roughly ≈(24000 samples/sec × 2 bytes/sample × 3 sec) ≈ 144 KB.
   * If your downloaded buffer is only 20 KB or 40 KB, it’s almost certainly an 8 kHz or compressed stream.

3. **Browser console errors/warnings:**

   * Look for warnings like “Using fallback JavaScript/vocoder due to missing WebGPU features.”
   * If it falls back to a JS vocoder, it might degrade the topology for speed, causing muffled output.

4. **Check the raw array in the console:**

   ```js
   console.log("first 32 bytes:", new Uint8Array(data).slice(0, 32));
   ```

   * You should see ASCII “RIFF” at the start. If you see odd bytes, your fetch/stream might have cut off early.

5. **Turn off “fast decode”:**

   * Some Chrome flags (e.g. `–enable‐fast‐skipped‐ranges`) can break `decodeAudioData`. Test in Edge or Firefox.

---

### Summary Checklist

1. **Request WAV at 24 kHz**

   ```js
   { codec: "wav", sampleRate: 24000 }
   ```
2. **Blob-test playback** (via `<audio>`)
3. **Console-log `audioBuffer.sampleRate`** after `decodeAudioData`
4. **Try Wasm backend vs WebGPU** to isolate precision/driver issues
5. **Ensure drivers/browser are up to date**

Once you confirm you’re truly getting a 24 kHz-WAV and that your decode/play path is correct, the muffling will vanish. In most cases the fix is simply “request `codec: 'wav'`” (so you aren’t stuck with 8 kHz-compressed audio) and decode it at the right sample rate. Good luck!

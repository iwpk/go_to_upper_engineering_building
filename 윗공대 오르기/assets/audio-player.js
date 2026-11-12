// AudioBufferSourceNode loops on the audio clock, without restarting a media element.
window.createLoopingBgm = function (fallback, encodedWav) {
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!Context || !encodedWav) return fallback;
  let context, gain, buffer, decoding, source = null;
  let offset = 0, startedAt = 0, version = 0, volume = .45, muted = false;
  function ensureContext() {
    if (!context) {
      context = new Context();
      gain = context.createGain();
      gain.gain.value = muted ? 0 : volume;
      gain.connect(context.destination);
    }
    return context;
  }
  function prepare() {
    if (!decoding) {
      const bytes = Uint8Array.from(atob(encodedWav), c => c.charCodeAt(0));
      decoding = ensureContext().decodeAudioData(bytes.buffer).then(decoded => {
        buffer = decoded;
        return decoded;
      });
    }
    return decoding;
  }
  function position() {
    const elapsed = source ? context.currentTime - startedAt : 0;
    return buffer ? (offset + elapsed) % buffer.duration : offset;
  }
  function pause() {
    version++;
    offset = position();
    if (source) {
      source.stop();
      source.disconnect();
      source = null;
    }
  }
  const player = {
    loop: true,
    get readyState() { return buffer ? 4 : 0; },
    get paused() { return source === null; },
    get currentTime() { return position(); },
    set currentTime(value) {
      const wasPlaying = source !== null;
      pause();
      offset = Math.max(0, Number(value) || 0);
      if (buffer) offset %= buffer.duration;
      if (wasPlaying) player.play().catch(() => {});
    },
    get volume() { return volume; },
    set volume(value) {
      volume = Math.max(0, Math.min(1, Number(value) || 0));
      if (gain) gain.gain.value = muted ? 0 : volume;
    },
    get muted() { return muted; },
    set muted(value) {
      muted = !!value;
      if (gain) gain.gain.value = muted ? 0 : volume;
    },
    async play() {
      if (source) return;
      const ticket = ++version;
      const ctx = ensureContext();
      await Promise.all([ctx.resume(), prepare()]);
      if (ticket !== version || source) return;
      offset %= buffer.duration;
      source = ctx.createBufferSource();
      source.buffer = buffer;
      source.loop = true;
      source.loopStart = 0;
      source.loopEnd = buffer.duration;
      source.connect(gain);
      startedAt = ctx.currentTime;
      source.start(0, offset);
    },
    pause
  };
  return player;
};

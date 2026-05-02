from AppKit import NSSound


class NSSoundBackend:
    def __init__(self):
        self.sound = None
        self.current_path = None
        self.paused = False
        self.stopped = True

    def play(self, path):
        sound = NSSound.alloc().initWithContentsOfFile_byReference_(str(path), True)
        if sound is None:
            raise RuntimeError(f"Unable to play {path.name}.")

        self.stop()
        self.sound = sound
        self.current_path = path
        self.paused = False
        self.stopped = False
        self.sound.play()

    def toggle_pause(self):
        if not self.sound:
            return None

        if self.paused:
            self.sound.resume()
            self.paused = False
        else:
            self.sound.pause()
            self.paused = True

        return self.paused

    def stop(self):
        if self.sound:
            self.sound.stop()

        self.sound = None
        self.current_path = None
        self.paused = False
        self.stopped = True

    def current_time(self):
        if not self.sound:
            return 0.0
        return float(self.sound.currentTime())

    def duration(self):
        if not self.sound:
            return 0.0
        return float(self.sound.duration())

    def seek(self, seconds):
        if not self.sound:
            return

        duration = self.duration()
        target = min(max(0.0, float(seconds)), duration if duration > 0 else float(seconds))
        self.sound.setCurrentTime_(target)

    def is_playing(self):
        return bool(self.sound and self.sound.isPlaying())

    def finished(self):
        if not self.sound or self.stopped or self.paused:
            return False

        if self.sound.isPlaying():
            return False

        duration = self.duration()
        if duration <= 0:
            return False

        return self.current_time() >= max(0.0, duration - 0.25)

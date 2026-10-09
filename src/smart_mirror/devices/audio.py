"""One speaker channel; pygame performs playback asynchronously."""
import pygame


class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()

    def play(self, file_path):
        self.stop()
        pygame.mixer.music.load(str(file_path))
        pygame.mixer.music.play()

    def stop(self):
        pygame.mixer.music.stop()

    def close(self):
        self.stop()
        pygame.mixer.quit()

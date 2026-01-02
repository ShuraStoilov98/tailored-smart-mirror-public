# file: audio_helper.py
import pygame
from threading import Thread
from time import sleep

class AudioPlayer:
    def __init__(self):
        pygame.mixer.init()
        self._thread = None

    def _play_file(self, file_path: str):
        """Internal function to play an audio file (blocking)."""
        pygame.mixer.music.load(file_path)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            sleep(0.1)

    def play(self, file_path: str):
        """Play audio in a non-blocking thread."""
        if self._thread and self._thread.is_alive():
            # Stop current audio if already playing
            pygame.mixer.music.stop()
            self._thread.join()

        self._thread = Thread(target=self._play_file, args=(file_path,), daemon=True)
        self._thread.start()

    def stop(self):
        """Stop any currently playing audio."""
        if self._thread and self._thread.is_alive():
            pygame.mixer.music.stop()
            self._thread.join()

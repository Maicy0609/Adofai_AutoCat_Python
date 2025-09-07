import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import time
import os
from pynput import keyboard
from pynput.keyboard import Key, Controller as KeyboardController
import adofaipy

class AdofaiAutoCat:
    def __init__(self, master):
        self.master = master
        master.title("Adofai Auto Cat (Python)")
        master.geometry("270x100")
        master.resizable(False, False)

        self.adofai_level = None
        self.is_playing = False
        self.playback_thread = None
        self.global_offset_ns = 0  # Global offset in nanoseconds
        self.keyboard_controller = KeyboardController()
        self.listener = None
        self.start_time_ns = 0

        self.label_file = tk.Label(master, text="未选择文件")
        self.label_file.pack(pady=5)

        self.btn_select_file = tk.Button(master, text="选择谱面文件", command=self.select_file)
        self.btn_select_file.pack(pady=5)

        self.label_status = tk.Label(master, text="", fg="green")
        self.label_status.pack(pady=5)

        self.last_file_path = None

        self.setup_global_hotkeys()

        master.protocol("WM_DELETE_WINDOW", self.on_closing)

    def select_file(self):
        file_path = filedialog.askopenfilename(
            initialdir=self.last_file_path if self.last_file_path else os.getcwd(),
            title="选择冰与火谱面文件",
            filetypes=(("冰与火谱面文件", "*.adofai"), ("所有文件", "*.*" ))
        )
        if file_path:
            self.last_file_path = os.path.dirname(file_path)
            self.label_file.config(text=f"已选择文件 - {os.path.basename(file_path)}")
            try:
                self.adofai_level = adofaipy.Level.load(file_path)
                self.label_status.config(text="谱面加载成功！", fg="green")
            except Exception as e:
                messagebox.showerror("错误", f"无法解析谱面: {e}")
                self.adofai_level = None
                self.label_status.config(text="解析错误", fg="red")

    def setup_global_hotkeys(self):
        def on_press(key):
            try:
                if key == Key.insert:
                    self.toggle_playback()
                elif key == Key.left:
                    if self.is_playing:
                        self.global_offset_ns -= 5 * 10**6  # -5ms
                        self.master.after(0, lambda: self.label_status.config(text=f"延迟调整: {self.global_offset_ns / 10**6:.0f}ms", fg="blue"))
                elif key == Key.right:
                    if self.is_playing:
                        self.global_offset_ns += 5 * 10**6  # +5ms
                        self.master.after(0, lambda: self.label_status.config(text=f"延迟调整: {self.global_offset_ns / 10**6:.0f}ms", fg="blue"))
            except AttributeError:
                pass

        self.listener = keyboard.Listener(on_press=on_press)
        self.listener.start()

    def toggle_playback(self):
        if self.adofai_level is None:
            messagebox.showwarning("警告", "请先选择一个谱面文件！")
            return

        if self.is_playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        if self.playback_thread and self.playback_thread.is_alive():
            return

        self.is_playing = True
        self.label_status.config(text="运行中...", fg="orange")
        self.playback_thread = threading.Thread(target=self._playback_loop)
        self.playback_thread.daemon = True
        self.playback_thread.start()

    def stop_playback(self):
        self.is_playing = False
        if self.playback_thread:
            self.playback_thread.join(timeout=0.1) # Give a small chance for thread to exit cleanly
        self.label_status.config(text="已停止", fg="red")

    def _playback_loop(self):
        try:
            events = []
            current_time_beats = 0.0

            # Adofai game has a 4-beat countdown (4, 3, 2, 1) before the first tile
            initial_countdown_beats = 4.0

            for i, tile in enumerate(self.adofai_level.tiles):
                tile_hit_time_seconds = self.adofai_level.get_time_from_beats(current_time_beats)
                tile_hit_time_ns = int(tile_hit_time_seconds * 1_000_000_000)

                events.append((tile_hit_time_ns, 'press'))

                if tile.hold_duration > 0:
                    hold_end_time_beats = current_time_beats + tile.hold_duration
                    hold_end_time_seconds = self.adofai_level.get_time_from_beats(hold_end_time_beats)
                    hold_end_time_ns = int(hold_end_time_seconds * 1_000_000_000)
                    events.append((hold_end_time_ns, 'release'))
                else:
                    events.append((tile_hit_time_ns + 10 * 10**6, 'release')) # 10ms after press

                if i < len(self.adofai_level.tiles) - 1:
                    current_time_beats += self.adofai_level.get_duration_for_tile(i)

            countdown_duration_ns = int(self.adofai_level.get_time_from_beats(initial_countdown_beats) * 1_000_000_000)
            events = [(t + countdown_duration_ns, type) for t, type in events]

            events.sort(key=lambda x: x[0])

            self.start_time_ns = time.perf_counter_ns()
            event_idx = 0

            while self.is_playing and event_idx < len(events):
                current_event_time_ns, event_type = events[event_idx]
                
                target_time_ns = current_event_time_ns + self.global_offset_ns

                elapsed_time_ns = time.perf_counter_ns() - self.start_time_ns
                time_to_wait_ns = target_time_ns - elapsed_time_ns

                if time_to_wait_ns > 0:
                    time.sleep(time_to_wait_ns / 1_000_000_000)
                
                if not self.is_playing:
                    break

                if event_type == 'press':
                    self.keyboard_controller.press(Key.space)
                elif event_type == 'release':
                    self.keyboard_controller.release(Key.space)
                
                event_idx += 1

            self.stop_playback()

        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("播放错误", f"自动播放过程中发生错误: {e}"))
            self.stop_playback()

    def on_closing(self):
        if self.listener:
            self.listener.stop()
        if self.playback_thread and self.playback_thread.is_alive():
            self.stop_playback()
        self.master.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = AdofaiAutoCat(root)
    root.mainloop()



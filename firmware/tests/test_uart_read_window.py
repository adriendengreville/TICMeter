"""Run the real read-window/UART functions with deterministic host UART events."""

import ctypes
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_stability_regressions import function_body, read_source


STUBS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <setjmp.h>

#define LINKY_BUFFER_SIZE (16 * 1024)
#define LINKY_DECODE_LEN (LINKY_BUFFER_SIZE - 1024)
#define LINKY_UART 1
#define portMAX_DELAY 0xffffffff
#define portTICK_PERIOD_MS 1
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGD(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define ESP_LOGE(...) ((void)0)
#define LED_LINKY_READING 1
#define LED_LINKY_FAILED 2
#define MODE_STD 1
#define TAG "LINKY"
typedef unsigned TickType_t;
typedef struct { int type; size_t size; } uart_event_t;
enum { UART_DATA, UART_FIFO_OVF, UART_BUFFER_FULL, UART_BREAK, UART_PARITY_ERR, UART_FRAME_ERR };
static int queue, mutex;
static void *linky_uart_queue = &queue;
static void *linky_buffer_mutex = &mutex;
static unsigned char linky_buffer[LINKY_BUFFER_SIZE];
static uint32_t linky_frame_size, linky_same_feilds_count, clock_ms;
static int linky_reading, linky_mode, lock_depth, pm_depth;
static bool uart_error, receiving, auto_retry;
static int decoded[3], decode_calls, read_calls, flush_calls, queued_idle;
static jmp_buf uart_return;
static bool event_pending;
static uart_event_t next_event;
#define MILLIS clock_ms
static void uart_event_task(void *unused);
static void run_uart(size_t size);

static void xSemaphoreTake(void *m, unsigned timeout)
{
    (void)timeout;
    assert(m == linky_buffer_mutex && lock_depth == 0);
    lock_depth = 1;
}
static void xSemaphoreGive(void *m)
{
    assert(m == linky_buffer_mutex && lock_depth == 1);
    lock_depth = 0;
    if (queued_idle) {
        queued_idle = 0;
        run_uart(8);
    }
}
static int xQueueReceive(void *q, void *event, unsigned timeout)
{
    (void)q; (void)timeout;
    if (!event_pending) longjmp(uart_return, 1);
    event_pending = false;
    *(uart_event_t *)event = next_event;
    return 1;
}
static void xQueueReset(void *q) { (void)q; }
static void uart_flush_input(int uart) { (void)uart; flush_calls++; }
static int uart_read_bytes(int uart, void *buffer, size_t size, unsigned timeout)
{
    (void)uart; (void)timeout;
    assert(lock_depth == 1 && linky_reading);
    memset(buffer, 'A', size);
    read_calls++;
    return (int)size;
}
static char linky_decode(void)
{
    assert(lock_depth == 1);
    assert(decode_calls < 3);
    decoded[decode_calls++] = (int)linky_frame_size;
    // A UART event arrives while the final decoder holds the mutex. It runs
    // only after release, when the read window has already been finalized.
    if (!linky_reading) queued_idle = 1;
    if (auto_retry && decode_calls == 1) return 2;
    return linky_frame_size ? 1 : 0;
}
static void run_uart(size_t size)
{
    next_event.type = UART_DATA;
    next_event.size = size;
    event_pending = true;
    if (setjmp(uart_return) == 0) uart_event_task(NULL);
}
static void vTaskDelay(unsigned ticks)
{
    clock_ms += ticks;
    if (receiving) run_uart((ticks * 512) / 1000);
}
static void vTaskDelete(void *task) { (void)task; }
static void linky_acquire_read_locks(void) { assert(pm_depth == 0); pm_depth++; }
static void linky_release_read_locks(void) { assert(pm_depth == 1); pm_depth--; }
static void led_start_pattern(int pattern) { (void)pattern; }
static void led_stop_pattern(int pattern) { (void)pattern; }
static void linky_stats(void) { }
'''

HARNESS = r'''
static void reset(void)
{
    linky_frame_size = linky_same_feilds_count = clock_ms = 0;
    linky_reading = lock_depth = pm_depth = 0;
    decode_calls = read_calls = flush_calls = queued_idle = 0;
    memset(decoded, 0, sizeof(decoded));
    receiving = true;
    auto_retry = uart_error = false;
    linky_mode = MODE_STD;
}
int idle_preserves_buffer(void)
{
    reset();
    linky_frame_size = 1234;
    run_uart(32);
    assert(read_calls == 0 && flush_calls == 1 && lock_depth == 0);
    return (int)linky_frame_size;
}
int capture_window(int retry, int data)
{
    reset();
    auto_retry = retry;
    receiving = data;
    int result = linky_update(15000);
    assert(lock_depth == 0 && pm_depth == 0 && linky_reading == 0);
    assert(linky_frame_size == 0);
    return result;
}
int decoded_bytes(int index) { return decoded[index]; }
int decoding_count(void) { return decode_calls; }
int start_discards_previous_window(void)
{
    reset();
    linky_frame_size = 800;
    uart_error = true;
    linky_begin_read_window();
    assert(linky_reading && !uart_error && flush_calls == 1 && lock_depth == 0);
    return (int)linky_frame_size;
}
'''


class UartReadWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="ticmeter-uart-")
        cls.addClassCleanup(cls.temp.cleanup)
        source = read_source("main/linky.c")
        functions = "\n".join(
            declaration + "\n{" + function_body(source, name) + "\n}\n"
            for declaration, name in [
                ("static void uart_event_task(void *pvParameters)", "uart_event_task"),
                ("static void linky_begin_read_window(void)", "linky_begin_read_window"),
                ("static char linky_end_read_window(void)", "linky_end_read_window"),
                ("char linky_update(uint32_t timeout)", "linky_update"),
            ]
        )
        path = Path(cls.temp.name)
        (path / "uart.c").write_text(STUBS + functions + HARNESS)
        compiler = shutil.which("cc")
        if compiler is None:
            raise RuntimeError("A C compiler is required for UART regression tests")
        result = subprocess.run(
            [compiler, "-std=c11", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
             "-Wno-unused-parameter", str(path / "uart.c"), "-o", str(path / "uart.so")],
            capture_output=True, text=True,
        )
        if result.returncode:
            raise RuntimeError(result.stderr)
        cls.lib = ctypes.CDLL(str(path / "uart.so"))
        cls.lib.capture_window.argtypes = [ctypes.c_int, ctypes.c_int]
        cls.lib.decoded_bytes.argtypes = [ctypes.c_int]

    def test_idle_uart_event_preserves_captured_software_buffer(self):
        self.assertEqual(self.lib.idle_preserves_buffer(), 1234)

    def test_final_decode_receives_partial_buffer_below_force_decode_threshold(self):
        self.assertEqual(self.lib.capture_window(0, 1), 1)
        self.assertEqual(self.lib.decoding_count(), 1)
        self.assertEqual(self.lib.decoded_bytes(0), 15 * 512)

    def test_auto_retry_collects_new_uart_bytes(self):
        self.assertEqual(self.lib.capture_window(1, 1), 1)
        self.assertEqual(self.lib.decoding_count(), 2)
        self.assertEqual(self.lib.decoded_bytes(1), 5 * 512)

    def test_no_uart_data_still_reports_decode_failure(self):
        self.assertEqual(self.lib.capture_window(0, 0), 0)
        self.assertEqual(self.lib.decoded_bytes(0), 0)

    def test_start_of_window_discards_stale_data(self):
        self.assertEqual(self.lib.start_discards_previous_window(), 0)


if __name__ == "__main__":
    unittest.main()

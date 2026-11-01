from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def read_source(relative_path):
    return (ROOT / relative_path).read_text(encoding="utf-8")


def function_body(source, name):
    match = re.search(rf"^[\w\s\*_]+{name}\s*\([^)]*\)\s*\{{", source, re.M)
    assert match, f"{name} not found"
    start = match.end()
    depth = 1
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError(f"{name} body not closed")


class StabilityRegressionTests(unittest.TestCase):
    def test_mqtt_publish_is_prepared_after_wifi_connect(self):
        body = function_body(read_source("main/main.c"), "main_send_data")
        wifi_connect_at = body.index("ret = wifi_connect();")
        prepare_at = body.index("mqtt_prepare_publish(data);")

        self.assertLess(wifi_connect_at, prepare_at)

    def test_failed_mqtt_state_retries_without_immediate_send_failure(self):
        body = function_body(read_source("main/mqtt.c"), "mqtt_send")
        failed_branch = re.search(
            r"if\s*\(\s*mqtt_state\s*==\s*MQTT_FAILED\s*\)\s*\{(?P<body>.*?)\n\s*\}",
            body,
            re.S,
        )
        self.assertIsNotNone(failed_branch, "MQTT_FAILED branch not found")

        self.assertNotIn("goto error", failed_branch.group("body"))

    def test_mqtt_send_timeout_allows_home_assistant_discovery_burst(self):
        source = read_source("main/mqtt.c")
        match = re.search(r"#define\s+MQTT_SEND_TIMEOUT\s+(\d+)", source)
        self.assertIsNotNone(match, "MQTT_SEND_TIMEOUT not found")

        self.assertGreaterEqual(int(match.group(1)), 30000)

    def test_mqtt_send_aborts_when_outbox_stops_draining(self):
        source = read_source("main/mqtt.c")
        body = function_body(source, "mqtt_send")

        self.assertRegex(source, r"#define\s+MQTT_SEND_STALL_TIMEOUT\s+5000")
        self.assertIn("mqtt_stall_timeout", body)
        self.assertIn("outbox stalled", body)

    def test_linky_decode_does_not_scan_past_received_buffer(self):
        body = function_body(read_source("main/linky.c"), "linky_decode")

        self.assertNotIn("i < linky_frame_size + 1", body)
        self.assertIn("i < linky_frame_size", body)

    def test_home_assistant_discovery_does_not_delete_transient_invalid_values(self):
        source = read_source("main/mqtt.c")
        body = function_body(source, "mqtt_setup_ha_discovery")

        self.assertIn("mqtt_linky_value_is_supported", body)
        self.assertIn("mqtt_linky_value_is_valid", body)
        self.assertIn("delete = !supported", body)

    def test_standard_instantaneous_power_is_real_time(self):
        source = read_source("main/linky.c")

        for label in ("SINSTS", "SINSTS1", "SINSTS2", "SINSTS3"):
            self.assertRegex(
                source,
                rf'"{label}",\s*&linky_data\.std\.{label},\s*UINT32,\s*0,\s*MODE_STD,\s*C_ANY,\s*G_(?:MONO|TRI),\s*REAL_TIME,\s*POWER_VA',
                f"{label} must be reported as a real-time measurement",
            )

    def test_uart_task_discards_tic_bytes_outside_read_window(self):
        body = function_body(read_source("main/linky.c"), "uart_event_task")

        self.assertIn("!linky_reading", body)
        self.assertIn("uart_flush_input(LINKY_UART)", body)
        self.assertIn("linky_frame_size = 0", body)

    def test_linky_update_flushes_stale_uart_data_before_reading(self):
        body = function_body(read_source("main/linky.c"), "linky_update")

        self.assertLess(body.index("linky_frame_size = 0"), body.index("linky_reading = 1"))
        self.assertLess(body.index("uart_flush_input(LINKY_UART)"), body.index("linky_reading = 1"))

    def test_uart_task_no_longer_decodes_small_partial_buffers(self):
        source = read_source("main/linky.c")

        self.assertRegex(source, r"#define\s+LINKY_DECODE_LEN\s+\(LINKY_BUFFER_SIZE - 1024\)")
        self.assertNotIn("#define LINKY_DECODE_LEN 512", source)

    def test_linky_uart_uses_stable_xtal_clock(self):
        source = read_source("main/linky.c")
        body = function_body(source, "linky_set_mode")

        self.assertIn(".source_clk = UART_SCLK_XTAL", body)
        self.assertNotIn(".source_clk = UART_SCLK_DEFAULT", body)

    def test_linky_uart_rx_uses_internal_pullup(self):
        body = function_body(read_source("main/linky.c"), "linky_set_mode")

        self.assertIn("gpio_pullup_en(linky_uart_rx)", body)
        self.assertIn("gpio_pulldown_dis(linky_uart_rx)", body)

    def test_linky_read_window_holds_cpu_clock_temporarily(self):
        source = read_source("main/linky.c")
        init_body = function_body(source, "linky_init")
        update_body = function_body(source, "linky_update")

        self.assertIn("ESP_PM_CPU_FREQ_MAX", init_body)
        self.assertIn("linky_acquire_read_locks();", update_body)
        self.assertIn("linky_release_read_locks();", update_body)

    def test_successful_send_does_not_clear_last_good_linky_values(self):
        body = function_body(read_source("main/main.c"), "main_send_data")

        self.assertNotIn("linky_clear_data();", body)
        self.assertIn('ESP_LOGI(MAIN_TAG, "Data sent")', body)

    def test_failed_read_publishes_last_known_linky_values(self):
        body = function_body(read_source("main/main.c"), "main_task")

        self.assertIn("Linky update failed", body)
        self.assertIn("if (!linky_presence())", body)
        self.assertIn("Publishing last known Linky data", body)

    def test_decode_failure_does_not_clear_last_good_linky_values(self):
        body = function_body(read_source("main/linky.c"), "linky_update")

        failure_case = re.search(r"case 0:(?P<body>.*?)case 2:", body, re.S)
        self.assertIsNotNone(failure_case)
        self.assertNotIn("linky_clear_data();", failure_case.group("body"))


if __name__ == "__main__":
    unittest.main()

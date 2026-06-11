import unittest

from musorg.utils.debug import add_log_observer, log, remove_log_observer, warning


class DebugObserverTests(unittest.TestCase):
    def test_log_observer_receives_events(self):
        events = []

        def observer(event: dict) -> None:
            events.append(event)

        add_log_observer(observer)
        try:
            log("Scan", "Found files", "🔎")
            warning("Metadata", "Missing tag")
        finally:
            remove_log_observer(observer)

        self.assertEqual([event["stage"] for event in events], ["Scan", "Metadata"])
        self.assertEqual([event["level"] for event in events], ["info", "warning"])

    def test_removed_log_observer_stops_receiving_events(self):
        events = []

        def observer(event: dict) -> None:
            events.append(event)

        add_log_observer(observer)
        remove_log_observer(observer)
        log("Scan", "Should not be captured", "🔎")

        self.assertEqual(events, [])

import unittest
from unittest.mock import Mock

from audio_player.ui_updates import ThrottledCallback


class ThrottledCallbackTests(unittest.TestCase):
    def test_burst_queues_one_draw_using_the_latest_size(self):
        scheduler = Mock()
        size = {"width": 100}
        drawn_sizes = []
        redraw = ThrottledCallback(scheduler, lambda: drawn_sizes.append(size["width"]))

        for width in range(100, 200):
            size["width"] = width
            redraw.request()

        scheduler.after.assert_called_once_with(16, redraw.run)
        self.assertEqual(drawn_sizes, [])
        scheduler.after.call_args.args[1]()
        self.assertEqual(drawn_sizes, [199])

    def test_continuous_requests_do_not_postpone_the_draw(self):
        scheduler = Mock()
        callback = Mock()
        redraw = ThrottledCallback(scheduler, callback, interval_ms=20)

        for _ in range(3):
            for _ in range(50):
                redraw.request()
            scheduler.after.call_args.args[1]()

        self.assertEqual(scheduler.after.call_count, 3)
        self.assertEqual(callback.call_count, 3)
        scheduler.after_cancel.assert_not_called()
        self.assertTrue(all(call.args[0] == 20 for call in scheduler.after.call_args_list))

    def test_request_during_callback_can_queue_the_next_frame(self):
        scheduler = Mock()
        redraw = ThrottledCallback(scheduler, lambda: redraw.request())
        redraw.request()

        scheduler.after.call_args.args[1]()

        self.assertEqual(scheduler.after.call_count, 2)

    def test_pending_job_with_zero_id_is_not_replaced(self):
        scheduler = Mock()
        scheduler.after.return_value = 0
        redraw = ThrottledCallback(scheduler, Mock())

        redraw.request()
        redraw.request()

        scheduler.after.assert_called_once()


if __name__ == "__main__":
    unittest.main()

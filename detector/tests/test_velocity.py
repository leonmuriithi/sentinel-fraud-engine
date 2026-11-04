import unittest

from sentinel.velocity import VelocityTracker
from tests.fakes import DownRedis, FakeRedis


class VelocityTrackerTests(unittest.TestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.tracker = VelocityTracker(self.redis, window_seconds=3600, location_jump_seconds=60)

    def test_cache_miss_is_treated_as_first_transaction(self):
        s = self.tracker.observe("u1", "Nairobi", now=1000.0)
        self.assertEqual(s.velocity, 1)
        self.assertFalse(s.location_jump)
        self.assertFalse(s.degraded)

    def test_velocity_counts_transactions_inside_window(self):
        for i in range(3):
            s = self.tracker.observe("u1", "Nairobi", now=1000.0 + i)
        self.assertEqual(s.velocity, 3)

    def test_old_transactions_expire_from_window(self):
        self.tracker.observe("u1", "Nairobi", now=0.0)
        self.tracker.observe("u1", "Nairobi", now=100.0)
        s = self.tracker.observe("u1", "Nairobi", now=4000.0)
        self.assertEqual(s.velocity, 1)

    def test_users_are_tracked_independently(self):
        self.tracker.observe("u1", "Nairobi", now=1000.0)
        self.tracker.observe("u1", "Nairobi", now=1001.0)
        self.assertEqual(self.tracker.observe("u2", "Nairobi", now=1002.0).velocity, 1)

    def test_location_jump_within_window_is_detected(self):
        self.tracker.observe("u1", "Nairobi", now=1000.0)
        s = self.tracker.observe("u1", "Lagos", now=1030.0)
        self.assertTrue(s.location_jump)

    def test_same_location_is_not_a_jump(self):
        self.tracker.observe("u1", "Nairobi", now=1000.0)
        self.assertFalse(self.tracker.observe("u1", "Nairobi", now=1010.0).location_jump)

    def test_location_change_after_window_is_not_a_jump(self):
        self.tracker.observe("u1", "Nairobi", now=1000.0)
        self.assertFalse(self.tracker.observe("u1", "Lagos", now=1500.0).location_jump)

    def test_malformed_cached_location_is_ignored(self):
        self.redis.strings["sentinel:loc:u1"] = "garbage-without-separator"
        s = self.tracker.observe("u1", "Nairobi", now=1000.0)
        self.assertFalse(s.location_jump)
        self.assertFalse(s.degraded)

    def test_redis_outage_degrades_instead_of_raising(self):
        tracker = VelocityTracker(DownRedis())
        s = tracker.observe("u1", "Nairobi", now=1000.0)
        self.assertTrue(s.degraded)
        self.assertEqual(s.velocity, 1)
        self.assertFalse(s.location_jump)


if __name__ == "__main__":
    unittest.main()

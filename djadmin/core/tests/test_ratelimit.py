"""R051: enforce_ip_limit считает по клиентскому IP (XFF), а не по IP прокси."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, TestCase

from core.ratelimit import RateLimitExceeded, RateLimitUnavailable, enforce_ip_limit


def _clear(bucket, ip):
    cache.delete("rl:ip:%s:%s" % (bucket, ip))


class ClientIpLimitTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_limit_by_remote_addr_without_xff(self):
        request = self.factory.get("/login")
        _clear("t1", "127.0.0.1")
        self.assertEqual(enforce_ip_limit(request, "t1", 2, 60), 1)
        self.assertEqual(enforce_ip_limit(request, "t1", 2, 60), 2)
        with self.assertRaises(RateLimitExceeded) as ctx:
            enforce_ip_limit(request, "t1", 2, 60)
        self.assertEqual(ctx.exception.retry_after, 60)

    def test_last_xff_hop_defines_the_bucket(self):
        # client_ip() берёт ПОСЛЕДНИЙ hop XFF (его дописывает доверенный прокси),
        # поэтому спуф-префикс не раздувает бакеты и не обходит лимит.
        request_a = self.factory.get("/login", HTTP_X_FORWARDED_FOR="1.2.3.4, 9.9.9.9")
        request_b = self.factory.get("/login", HTTP_X_FORWARDED_FOR="5.6.7.8, 9.9.9.9")
        request_other = self.factory.get("/login", HTTP_X_FORWARDED_FOR="5.6.7.8, 8.8.8.8")
        _clear("t2", "9.9.9.9")
        _clear("t2", "8.8.8.8")
        self.assertEqual(enforce_ip_limit(request_a, "t2", 2, 60), 1)
        self.assertEqual(enforce_ip_limit(request_b, "t2", 2, 60), 2)  # тот же последний hop
        with self.assertRaises(RateLimitExceeded):
            enforce_ip_limit(request_a, "t2", 2, 60)
        # другой последний hop — независимый бакет
        self.assertEqual(enforce_ip_limit(request_other, "t2", 2, 60), 1)

    def test_cache_failure_is_fail_closed(self):
        request = self.factory.get("/login")
        with patch.object(cache, "add", side_effect=RuntimeError("redis down")):
            with self.assertRaises(RateLimitUnavailable):
                enforce_ip_limit(request, "t3", 5, 60)

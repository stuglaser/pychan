#!/usr/bin/env python
#
# Examples from the talk:
#   Sameer Ajmani - Advanced Go Concurrency Patterns - Google I/O 2013
#   https://www.youtube.com/watch?v=QDDwwePbDtw
#   https://code.google.com/p/go/source/browse/2013/advconc?repo=talks
import argparse
import collections
import random
import threading
import time

from chan import Chan, chanselect, quickthread


MOCK_POSTS = [
    'First post from ',
    'This is the second post from ',
    'A third post?  How interesting.  Thanks ',
    'Woah!  A fourth post from '
]

Item = collections.namedtuple('Item', ['channel', 'title'])

class MockFetcher(object):
    def __init__(self, domain):
        self.domain = domain
        self.posts = [p + self.domain for p in MOCK_POSTS]

    def fetch(self):
        if not self.posts:
            return [], time.time() + 1000.0
        item_list = [Item(self.domain, self.posts.pop(0))]
        next_time = time.time() + random.random() * 0.2 + 0.1
        return item_list, next_time


def timeout_after(delay):
    def thread(ch):
        time.sleep(delay)
        ch.put(None)
    c = Chan()
    t = threading.Thread(name='timeout', target=thread, args=(c,))
    t.daemon = True
    t.start()
    return c


class Subscription(object):
    def __init__(self, fetcher):
        self.fetcher = fetcher
        self.updates_chan = Chan()
        self.quit = Chan()
        self.thread = threading.Thread(
            name='Subscription',
            target=self._run)
        #self.thread.daemon = True
        self.thread.start()

    def _run(self):
        next_time = time.time()
        pending = []  # First is most recent.  Should be a deque
        err = None

        while True:
            start_fetch = timeout_after(max(0.0, next_time - time.time()))

            # Does or doesn't wait on updates_chan depending on if we have
            # items ready.
            if pending:
                outchans = [(self.updates_chan, pending[0])]
            else:
                outchans = []

            ch, value = chanselect([self.quit, start_fetch], outchans)
            if ch == self.quit:
                errc = value
                self.updates_chan.close()
                errc.put(err)
                return
            elif ch == start_fetch:
                try:
                    err = None
                    item_list, next_time = self.fetcher.fetch()
                except Exception as ex:
                    err = ex
                    next_time = time.time() + 10.0
                    continue
                pending.extend(item_list)
            else:  # self.updates_chan
                pending.pop(0)  # Pops the sent item

    def updates(self):
        return self.updates_chan

    def close(self):
        errc = Chan()
        self.quit.put(errc)
        result = errc.get()
        self.thread.join(0.2)
        assert not self.thread.is_alive()
        return result


class Merged(object):
    def __init__(self, subscriptions):
        self.subscriptions = subscriptions
        self.updates_chan = Chan()
        self.quit = Chan()

        self.thread = threading.Thread(
            name="Merged",
            target=self._run)
        self.thread.start()

    def _close_subs_collect_errs(self):
        return [sub.close() for sub in self.subscriptions]

    def _run(self):
        subchans = [sub.updates() for sub in self.subscriptions]
        while True:
            c, value = chanselect(subchans + [self.quit], [])
            if c == self.quit:
                value.put(self._close_subs_collect_errs())
                self.updates_chan.close()
                return
            else:
                item = value

            c, _ = chanselect([self.quit], [(self.updates_chan, item)])
            if c == self.quit:
                value.put(self._close_subs_collect_errs())
                self.updates_chan.close()
                return
            else:
                pass  # Send successful

    def updates(self):
        return self.updates_chan

    def close(self):
        errc = Chan()
        self.quit.put(errc)
        result = errc.get()
        self.thread.join(timeout=0.2)
        assert not self.thread.is_alive()
        return result


def main():
    FetcherCls = MockFetcher

    merged = Merged([
        Subscription(FetcherCls('blog.golang.org')),
        Subscription(FetcherCls('googleblog.blogspot.com')),
        Subscription(FetcherCls('googledevelopers.blogspot.com'))])

    # Close after a while
    def close_later():
        time.sleep(3)
        print("Closed: {}".format(merged.close()))
    quickthread(close_later)

    for it in merged.updates():
        print("{} -- {}".format(it.channel, it.title))

    time.sleep(0.1)
    print("Still active:         (should only be _MainThread and timeouts)")
    for active in threading._active.itervalues():
        print("    {}".format(active))

if __name__ == '__main__':
    main()


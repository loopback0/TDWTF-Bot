#!/usr/bin/python
# -*- coding: utf8 -*-

from collections import namedtuple
from pprint import pprint
from time import time, sleep
import requests
import random
import re
import ConfigParser

REPLY_TO_PMS = True # If True, reply to private messages instead of mentions

BASE_URL = "http://what.thedailywtf.com"
MESSAGE = u"I agree with whatever @%s posted just above."

class WhatBot(object):
    """
    A Discourse bot.
    """

    class WorseThanFailure(Exception):
        pass

    Mention = namedtuple('Mention', ['username', 'topic_id', 'post_number'])

    def __init__(self):
        self._session = requests.Session()
        self._session.headers['X-Requested-With'] = "XMLHttpRequest"
        self._client_id = self._get_client_id()
        self._bus_registrations = {}
        self._bus_callbacks = {}
        self._nbsp_count = random.randrange(0, 50)

        config = ConfigParser.ConfigParser()
        config.read(['whatbot.conf'])
        self._config = config

    def run(self):
        # Get the CSRF token
        res = self._get("/session/csrf", _=int(time() * 1000))
        self._session.headers['X-CSRF-Token'] = res[u'csrf']

        # Login
        res = self._post("/session", login=self._config.get('Login'), password=self._config.get('Password'))
        if u'error' in res:
            raise self.WorseThanFailure(res[u'error'].encode('utf8'))

        my_uid = res[u'user'][u'id']

        self._bus_registrations["/notification/%d" % my_uid] = -1
        self._bus_callbacks["/notification/%d" % my_uid] = self._notif_cb

        self._session.headers['X-SILENCE-LOGGER'] = "true"

        self._handle_notifications()

        print "Entering main loop"
        while True:
            pprint(self._bus_registrations)
            data = self._post("/message-bus/%s/poll" % self._client_id,
                **self._bus_registrations)
            pprint(data)

            for message in data:
                channel = message[u'channel']
                if channel in self._bus_registrations:
                    message_id = message[u'message_id']
                    self._bus_registrations[channel] = message_id
                    self._bus_callbacks[channel](message[u'data'])
                if channel == u"/__status":
                    for key, value in message[u'data'].iteritems():
                        if key in self._bus_registrations:
                            self._bus_registrations[key] = value

    def _notif_cb(self, message):
        if REPLY_TO_PMS:
            count = message[u'unread_private_messages']
        else:
            count = message[u'unread_notifications']

        if count > 0:
            self._handle_notifications()

    def _handle_notifications(self):
        for mention in self._get_mentions():
            print u"Replying to %s in topic %d, post %d" % (mention.username,
                mention.topic_id, mention.post_number)

            sleep(.5)

            print u"Marking as read…"
            self._mark_as_read(mention.topic_id, mention.post_number)

            sleep(.5)

            print u"Sending reply…"
            message = MESSAGE % mention.username + (u"&nbsp;" *
                self._nbsp_count)
            self._nbsp_count = (self._nbsp_count + 1) % 50

            self._reply_to(mention.topic_id, mention.post_number, message)
            sleep(5)


    def _reply_to(self, topic_id, post_number, raw_message):
        # No idea what happens if we mix these up
        archetype = 'private_message' if REPLY_TO_PMS else 'regular'

        return self._post("/posts", raw=raw_message, topic_id=topic_id,
            reply_to_post_number=post_number,
            archetype=archetype
        )

    def _mark_as_read(self, topic_id, post_number):
        # Send fake timings
        # I hate special chars in POST keys
        kwargs = {
            'topic_id': topic_id,
            'topic_time': 400, # msecs passed on topic (I think)
            'timings[%d]' % post_number: 400 # msecs passed on post (same)
        }

        self._post("/topics/timings", **kwargs)


    def _get_mentions(self):
        watched_type = 6 if REPLY_TO_PMS else 1

        for notification in self._get("/notifications", _=int(time() * 1000)):
            if (notification[u'notification_type'] == watched_type and
                notification[u'read'] == False):
                data = notification[u'data']
                yield self.Mention(username=data[u'original_username'],
                    topic_id=notification[u'topic_id'],
                    post_number=notification[u'post_number'])

    @staticmethod
    def _get_client_id():
        def _replace(letter):
            val = random.randrange(0, 16)
            if letter == "x":
                val = (3 & val) | 8
            return "%x" % val

        return re.sub('[xy]', _replace, "xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx")

    def _get(self, url, **kwargs):
        r = self._session.get(BASE_URL + url, params=kwargs)
        r.raise_for_status()
        return r.json()

    def _post(self, url, **kwargs):
        r = self._session.post(BASE_URL + url, data=kwargs)
        if r.status_code == 422:
            raise self.WorseThanFailure(u",".join(r.json()[u'errors']))
        r.raise_for_status()
        if r.headers['Content-type'].startswith('application/json'):
            return r.json()
        return r.content

if __name__ == '__main__':
    WhatBot().run()

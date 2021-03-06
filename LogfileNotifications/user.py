# -*- coding: utf-8 -*-

import pprint
import threading
from datetime import datetime
import logging

from .bot import TelegramBot
from .notify import Notify


class User:
    telegram_bot = None
    logout_delay = 30  # delay in seconds for logout events
    log = logging.getLogger(__name__)

    def __init__(self, user_config, push_scheduler):
        self.online = False
        self.last_seen = None
        self.quiet_until = None
        self.nma = None
        self.offline_events = dict()
        self.cfg = user_config
        self.push_scheduler = push_scheduler

    def should_send_push(self, ignore_online=False):
        if not self.cfg['enabled'] \
                or (self.online and not ignore_online) \
                or (self.quiet_until is not None and self.quiet_until > datetime.now()):
            return False
        else:
            return True

    def push(self, title, message, ignore_online=False):
        # Remove this offline msg from offline_events queue
        if title == 'Logout' and message in self.offline_events:
            del self.offline_events[message]

        if not self.should_send_push(ignore_online):
            return

        thr = threading.Thread(target=self.push_sync, args=(title, message, ignore_online))
        thr.start()

    def inform_start(self):
        if 'start_msg' in self.cfg and self.cfg['start_msg'] is True:
            self.push_sync('Info', 'Restart')

    def push_sync(self, title, message, ignore_online=False):
        if not self.should_send_push(ignore_online):
            return

        User.log.debug('Informing {}'.format(self.cfg['name']))

        for method in self.cfg['notify_with']:
            try:
                Notify.notify(method, self, title, message)
            except Exception as exp:
                User.log.error('Error sending notification to user {}: {}'.format(self.cfg['name'], exp))

    def handle_event(self, event_nickname, server_name, event_name, check_field):
        if event_nickname in self.cfg['nicknames']:
            # Nickname belonged to this user
            self.last_seen = datetime.now()
            if event_name == 'Login':
                self.online = datetime.now()
            elif event_name == 'Logout':
                self.online = False
        else:
            if self.cfg[check_field]:
                if event_name == 'Login':
                    # Cancel offline event for nickname
                    # And don't send online event
                    if event_nickname in self.offline_events:
                        try:
                            self.push_scheduler.cancel(self.offline_events.pop(event_nickname))
                            User.log.info('Logoff msg to {} canceled'.format(self.cfg['name']))
                        except ValueError as err:
                            User.log.error('Error removing delayed event: ' + str(err))
                        return
                    title = 'Login ({})'.format(server_name)
                    self.push(title, event_nickname)
                else:
                    # Delay sending the logoff event (30s)
                    if self.should_send_push():
                        User.log.info('Scheduling Logoff msg to {} ({} sec delay)'
                                      .format(self.cfg['name'], User.logout_delay))
                        event = self.push_scheduler.enter(User.logout_delay, 1, self.push, (event_name, event_nickname))
                        self.offline_events[event_nickname] = event

    def __str__(self):
        ret = pprint.pformat(self.cfg, indent=4)
        ret += '\n' \
               'last_seen: {}\n' \
               'quiet_until: {}\n' \
               'online: {}'.format(TelegramBot.format_date(self.last_seen),
                                   TelegramBot.format_date(self.quiet_until),
                                   bool(self.online))
        return ret

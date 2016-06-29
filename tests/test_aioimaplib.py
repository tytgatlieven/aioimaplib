# -*- coding: utf-8 -*-
import asyncio
import email
import unittest

from aioimaplib import aioimaplib
from aioimaplib.aioimaplib import Commands, _split_responses
from tests.imapserver import imap_receive, Mail
from tests.test_imapserver import WithImapServer


class TestAioimaplibUtils(unittest.TestCase):
    def test_split_responses_no_data(self):
        self.assertEquals([], _split_responses(b''))

    def test_split_responses_regular_lines(self):
        self.assertEquals([b'* BYE Logging out', b'CAPB2 OK LOGOUT completed'],
                          _split_responses(b'* BYE Logging out\r\nCAPB2 OK LOGOUT completed\r\n'))

    def test_split_responses_with_message_data(self):
        self.assertEquals([b'* 1 FETCH (UID 1 RFC822 {26}\r\n...\r\n(mail content)\r\n...\r\n)',
                           b'TAG OK FETCH completed.'],
                          _split_responses(
                              b'* 1 FETCH (UID 1 RFC822 {26}\r\n...\r\n(mail content)\r\n...\r\n)\r\n'
                              b'TAG OK FETCH completed.'))

    def test_split_responses_with_two_messages_data(self):
        self.assertEquals([b'* 3 FETCH (UID 3 RFC822 {8}\r\nmail 1\r\n)',
                           b'* 4 FETCH (UID 4 RFC822 {8}\r\nmail 2\r\n)',
                           b'TAG OK FETCH completed.'],
                          _split_responses(
                              b'* 3 FETCH (UID 3 RFC822 {8}\r\nmail 1\r\n)\r\n'
                              b'* 4 FETCH (UID 4 RFC822 {8}\r\nmail 2\r\n)\r\n'
                              b'TAG OK FETCH completed.'))


class TestAioimaplib(WithImapServer):
    @asyncio.coroutine
    def test_capabilities(self):
        imap_client = aioimaplib.IMAP4(port=12345, loop=self.loop)
        yield from asyncio.wait_for(imap_client.wait_hello_from_server(), 2)

        self.assertEquals('IMAP4REV1', imap_client.protocol.imap_version)

    @asyncio.coroutine
    def test_login(self):
        imap_client = aioimaplib.IMAP4(port=12345, loop=self.loop, timeout=3)
        yield from asyncio.wait_for(imap_client.wait_hello_from_server(), 2)

        result, data = yield from imap_client.login('user', 'password')

        self.assertEquals(aioimaplib.AUTH, imap_client.protocol.state)
        self.assertEqual('OK', result)
        self.assertEqual('LOGIN completed', data[-1])

    @asyncio.coroutine
    def test_login_twice(self):
        with self.assertRaises(aioimaplib.Error) as expected:
            imap_client = yield from self.login_user('user', 'pass')

            yield from imap_client.login('user', 'password')

        self.assertEqual(expected.exception.args, ('command LOGIN illegal in state AUTH',))

    @asyncio.coroutine
    def test_logout(self):
        imap_client = yield from self.login_user('user', 'pass')

        result, data = yield from imap_client.logout()

        self.assertEqual('OK', result)
        self.assertEqual(['BYE Logging out', 'LOGOUT completed'], data)
        self.assertEquals(aioimaplib.LOGOUT, imap_client.protocol.state)

    @asyncio.coroutine
    def test_select_no_messages(self):
        imap_client = yield from self.login_user('user', 'pass')

        result, data = yield from imap_client.select()

        self.assertEqual('OK', result)
        self.assertEqual(['0'], data)
        self.assertEquals(aioimaplib.SELECTED, imap_client.protocol.state)

    @asyncio.coroutine
    def test_search_two_messages(self):
        imap_receive(Mail(['user']))
        imap_receive(Mail(['user']))
        imap_client = yield from self.login_user('user', 'pass', select=True)

        result, data = yield from imap_client.search('ALL')

        self.assertEqual('OK', result)
        self.assertEqual(['1 2'], data)

    @asyncio.coroutine
    def test_uid_with_illegal_command(self):
        imap_client = yield from self.login_user('user', 'pass', select=True)

        for command in {'COPY', 'FETCH', 'STORE'}.symmetric_difference(Commands.keys()):
            with self.assertRaises(aioimaplib.Abort) as expected:
                yield from imap_client.uid(command)

            self.assertEqual(expected.exception.args,
                             ('command UID only possible with COPY, FETCH or STORE (was %s)' % command,))

    @asyncio.coroutine
    def test_search_three_messages_by_uid(self):
        imap_client = yield from self.login_user('user', 'pass', select=True)
        imap_receive(Mail(['user']))  # id=1 uid=1
        imap_receive(Mail(['user']), mailbox='OTHER_MAILBOX')  # id=1 uid=2
        imap_receive(Mail(['user']))  # id=2 uid=3

        self.assertEqual(('OK', ['1 3']), (yield from imap_client.uid_search('ALL')))
        self.assertEqual(('OK', ['1 2']), (yield from imap_client.search('ALL')))

    @asyncio.coroutine
    def test_fetch(self):
        imap_client = yield from self.login_user('user', 'pass', select=True)
        mail = Mail(['user'], mail_from='me', subject='hello', content='pleased to meet you, wont you guess my name ?')
        imap_receive(mail)

        result, data = yield from imap_client.fetch('1', '(RFC822)')

        self.assertEqual('OK', result)
        self.assertEqual(['FETCH (UID 1 RFC822 {368}', str(mail).encode()], data)
        emaillib_decoded_msg = email.message_from_bytes(data[1])
        self.assertEqual('hello', emaillib_decoded_msg['Subject'])

    @asyncio.coroutine
    def test_fetch_by_uid(self):
        imap_client = yield from self.login_user('user', 'pass', select=True)
        mail = Mail(['user'], mail_from='me', subject='hello', content='pleased to meet you, wont you guess my name ?')
        imap_receive(mail)

        result, data = yield from imap_client.uid('fetch', '1', '(RFC822)')

        self.assertEqual('OK', result)
        self.assertEqual(['FETCH (UID 1 RFC822 {368}', str(mail).encode()], data)

    @asyncio.coroutine
    def login_user(self, login, password, select=False, lib=aioimaplib.IMAP4):
        imap_client = aioimaplib.IMAP4(port=12345, loop=self.loop, timeout=3)
        yield from asyncio.wait_for(imap_client.wait_hello_from_server(), 2)

        yield from imap_client.login('user', 'password')

        if select:
            yield from imap_client.select()
        return imap_client

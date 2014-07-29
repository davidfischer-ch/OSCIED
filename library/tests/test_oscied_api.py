#!/usr/bin/env python
# -*- encoding: utf-8 -*-

#**********************************************************************************************************************#
#              OPEN-SOURCE CLOUD INFRASTRUCTURE FOR ENCODING AND DISTRIBUTION : COMMON LIBRARY
#
#  Project Manager : Bram Tullemans (tullemans@ebu.ch)
#  Main Developer  : David Fischer (david.fischer.ch@gmail.com)
#  Copyright       : Copyright (c) 2012-2013 EBU. All rights reserved.
#
#**********************************************************************************************************************#
#
# This file is part of EBU Technology & Innovation OSCIED Project.
#
# This project is free software: you can redistribute it and/or modify it under the terms of the EUPL v. 1.1 as provided
# by the European Commission. This project is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See the European Union Public License for more details.
#
# You should have received a copy of the EUPL General Public License along with this project.
# If not, see he EUPL licence v1.1 is available in 22 languages:
#     22-07-2013, <https://joinup.ec.europa.eu/software/page/eupl/licence-eupl>

from mock import call
from nose.tools import assert_equal, assert_raises
from pytoolbox.unittest import mock_cmd
from requests import get, post

from oscied_lib.api import VERSION, OsciedCRUDMapper, OrchestraAPIClient
from oscied_lib.models import User


class FakeAPIClient(object):
    def __init__(self, api_url, environment='maas'):
        self.api_url = api_url
        self.environment = environment
        self.do_request = mock_cmd()


class TestOsciedCRUDMapper(object):

    def test_get_url_without_environment(self):
        client = FakeAPIClient('http://test.com')
        mapper = OsciedCRUDMapper(client, id_prefix='id')
        assert_equal(mapper.get_url(), u'http://test.com')
        assert_equal(mapper.get_url(extra='extra_value'), u'http://test.com/extra_value')
        assert_equal(mapper.get_url(index='index_value'), u'http://test.com/id/index_value')
        assert_equal(mapper.get_url(index='index_value', extra='extra_value'),
                     u'http://test.com/id/index_value/extra_value')

    def test_get_url_with_environment(self):
        client = FakeAPIClient('http://test.com')
        mapper = OsciedCRUDMapper(client, id_prefix='id', environment=True)
        assert_equal(mapper.get_url(), u'http://test.com/environment/maas')
        assert_equal(mapper.get_url(extra='extra_value'), u'http://test.com/environment/maas/extra_value')
        assert_equal(mapper.get_url(index='index_value'), u'http://test.com/environment/maas/id/index_value')
        assert_equal(mapper.get_url(index='index_value', extra='extra_value'),
                     u'http://test.com/environment/maas/id/index_value/extra_value')

    def test_add_cls_none(self):
        client = FakeAPIClient('http://test.com')
        mapper = OsciedCRUDMapper(client, 'method')
        assert_raises(ValueError, mapper.add)
        assert_raises(ValueError, mapper.add, 10, arg=20)
        mapper.add('hello')
        mapper.add(arg1=0)
        assert_equal(client.do_request.call_args_list, [
            call(post, u'http://test.com/method', data='"hello"'),
            call(post, u'http://test.com/method', data='{"arg1": 0}')])

    def test_add_cls_user(self):
        client = FakeAPIClient('http://test.com')
        mapper = OsciedCRUDMapper(client, 'method', User, environment=True)
        user = User(first_name='Tabby', last_name='Fischer', mail='t@f.com', secret='mia0w_mia0w')
        user._id = '3959e400-94b0-49f7-8b0f-fd168b7c90e3'
        user.is_valid(True)
        mapper.add(user)
        assert_equal(client.do_request.call_args_list, [
            call(post, u'http://test.com/method/environment/maas',
                 data='{"first_name": "Tabby", "last_name": "Fischer", "admin_platform": false, "secret": "mia0w_mia0w"'
                      ', "mail": "t@f.com", "_id": "3959e400-94b0-49f7-8b0f-fd168b7c90e3"}')])


def assert_len(client, mapper, expected):
    client.do_request = mock_cmd()
    try:
        len(mapper)
    except:
        pass
    assert_equal(client.do_request.call_args_list, expected)


class TestOrchestraAPIClient(object):

    def test_len(self):
        client = OrchestraAPIClient('http://a.ch', 6000, auth=('username', 'password'))
        assert_equal(client.users.get_url(), 'http://a.ch:6000/api/{0}/user'.format(VERSION))
        assert_len(client, client.users, [call(get, u'http://a.ch:6000/api/{0}/user/count'.format(VERSION))])
        assert_len(client, client.medias, [call(get, u'http://a.ch:6000/api/{0}/media/count'.format(VERSION))])
        assert_len(client, client.environments, [call(get, u'http://a.ch:6000/api/{0}/environment/count'.format(VERSION))])
        assert_len(client, client.transform_profiles, [call(get, u'http://a.ch:6000/api/{0}/transform/profile/count'.format(VERSION))])
        #assert_len(client, client.transform_units, [call(get, u'http://a.ch:6000/transform/unit/count'.format(VERSION))])
        assert_len(client, client.transform_tasks, [call(get, u'http://a.ch:6000/api/{0}/transform/task/count'.format(VERSION))])

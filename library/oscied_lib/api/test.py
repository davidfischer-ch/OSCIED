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
#
# Retrieved from https://github.com/ebu/OSCIED

from __future__ import absolute_import, division, print_function, unicode_literals

import uuid
from nose.tools import assert_raises
from pytoolbox.exception import assert_raises_item
from ..models import User


def test_api(api_client, root_secret, node_secret):
    u"""Live-test security and functionalities of a running orchestrator."""

    print(api_client.about)
    root = (u'root', root_secret)
    node = (u'node', node_secret)

    print(u'Register some test users')
    api_client.auth = root
    admin = User(first_name=u'Admin', last_name=u'Test', mail=u'a@u.test', secret=u'AdminS3cret', admin_platform=True)
    user  = User(first_name=u'User',  last_name=u'Test', mail=u'u@u.test', secret=u'SimpleS3cret')
    admin = api_client.login_or_create(admin)
    user  = api_client.login_or_create(user)

    print(u'Test user API')

    print(u'\t1/3 Access control')

    # FIXME this is really not pythonic ...

    print(u'\t\tAnonymous ...')
    api_client.auth = None
    assert_raises(Exception, api_client.login, None, None)
    assert_raises(Exception, len, api_client.users)
    assert_raises(Exception, api_client.users.list)
    assert_raises_item(Exception, api_client.users, admin._id)
    assert_raises_item(Exception, api_client.users, admin._id, value=admin)
    assert_raises_item(Exception, api_client.users, admin._id, delete=True)

    print(u'\t\tCharlie ...')
    api_client.auth = (u'charlie', u'passw0rd')
    assert_raises(Exception, api_client.login, *api_client.auth)
    assert_raises(Exception, len, api_client.users)
    assert_raises(Exception, api_client.users.list)
    assert_raises_item(Exception, api_client.users, user._id)
    assert_raises_item(Exception, api_client.users, user._id, value=admin)
    assert_raises_item(Exception, api_client.users, user._id, delete=True)

    print(u'\t\tRoot ...')
    api_client.auth = root
    assert_raises(Exception, api_client.login, *api_client.auth)
    len(api_client.users)
    api_client.users
    api_client.users[admin._id]
    api_client.users[admin._id] = admin
    del api_client.users[user._id]
    user = api_client.users.add(user)

    print(u'\t\tNode ...')
    api_client.auth = node
    assert_raises(Exception, api_client.login, *api_client.auth)
    assert_raises(Exception, len, api_client.users)
    assert_raises(Exception, api_client.users.list)
    assert_raises_item(Exception, api_client.users, user._id)
    assert_raises_item(Exception, api_client.users, user._id, value=admin)
    assert_raises_item(Exception, api_client.users, user._id, delete=True)

    print(u'\t\tAdmin ...')
    api_client.login(admin)
    len(api_client.users)
    api_client.users.list()
    api_client.users[user._id]
    api_client.users[user._id] = user
    del api_client.users[user._id]
    user = api_client.users.add(user)

    print(u'\t\tUser ...')
    api_client.login(user)
    len(api_client.users)
    assert_raises(Exception, api_client.users.list)
    api_client.users[admin._id]
    api_client.users[user._id] = user
    assert_raises_item(Exception, api_client.users, admin._id, value=admin)
    assert_raises_item(Exception, api_client.users, admin._id, delete=True)
    del api_client.users[user._id]
    api_client.auth = admin
    user = api_client.users.add(user)

    print(u'\t2/3 Input validation ...')
    api_client.auth = admin
    assert_raises_item(TypeError, api_client.users, 0)
    assert_raises_item(IndexError, api_client.users, uuid.uuid4())
    assert_raises_item(IndexError, api_client.users, uuid.uuid4(), delete=True)

    # mecho 'Admin can modify users (and it should work as expected)'
    # test_api 200 PATCH $ORCHESTRA_URL/user/id/$user3_id "$user1_auth" \
    #   '{"first_name":"the", "last_name":"test"}'
    # test_api 200 PATCH $ORCHESTRA_URL/user/id/$user3_id "$user1_auth" \
    #   '{"mail":"t@t.com", "secret": "salutMe3"}'
    # test_api 200 GET   $ORCHESTRA_URL/user/login        't@t.com:salutMec3' ''
    # test_api 200 PATCH $ORCHESTRA_URL/user/id/$user3_id "$user1_auth"   "$user3_json"
    # test_api 200 GET   $ORCHESTRA_URL/user/login        "$user3_auth"   ''
    # mecho 'Admin can add/remove admin_platform role to users'
    # test_api 200 PATCH $ORCHESTRA_URL/user/id/$user2_id "$user1_auth" '{"admin_platform":true}'
    # test_api 200 GET   $ORCHESTRA_URL/user              "$user2_auth" ''
    # test_api 200 PATCH $ORCHESTRA_URL/user/id/$user2_id "$user1_auth" '{"admin_platform":false}'
    # test_api 403 GET   $ORCHESTRA_URL/user              "$user2_auth" ''
    # mecho 'Simple user cannot kill another, itself yes, but not 2x (Chuck Norris can)'
    # test_api 403 DELETE $ORCHESTRA_URL/user/id/$user1_id "$user3_auth" ''
    # test_api 200 DELETE $ORCHESTRA_URL/user/id/$user2_id "$user2_auth" ''
    # test_api 401 DELETE $ORCHESTRA_URL/user/id/$user2_id "$user2_auth" ''
    # test_api 401 GET    $ORCHESTRA_URL/user/login        "$user2_auth" ''
    # test_api 200 POST   $ORCHESTRA_URL/user              "$user1_auth" "$user2_json"
    # save_id 'user2' "$ID"
    # test_api 200 GET    $ORCHESTRA_URL/user/login        "$user2_auth" ''

    #users_count = len(client.users)
    #users = api_client.users.list()
    #assert_equal(users_count, len(users))

# api_test_main()
# {
#   pecho 'Test main API'
#   test_api 401 POST $ORCHESTRA_URL/flush ''            ''
#   test_api 401 POST $ORCHESTRA_URL/flush "$BAD_AUTH"   ''
#   test_api 403 POST $ORCHESTRA_URL/flush "$user2_auth" ''
#   test_api 200 GET  $ORCHESTRA_URL       ''            ''
#   test_api 200 GET  $ORCHESTRA_URL/index ''            ''
#   test_api 200 GET  $ORCHESTRA_URL       "$BAD_AUTH"   ''
#   test_api 200 GET  $ORCHESTRA_URL/index "$BAD_AUTH"   ''
#   test_api 200 GET  $ORCHESTRA_URL       "$ROOT_AUTH"  ''
#   test_api 200 GET  $ORCHESTRA_URL/index "$ROOT_AUTH"  ''
#   test_api 200 GET  $ORCHESTRA_URL       "$NODE_AUTH"  ''
#   test_api 200 GET  $ORCHESTRA_URL/index "$NODE_AUTH"  ''
#   test_api 200 GET  $ORCHESTRA_URL       "$user1_auth" ''
#   test_api 200 GET  $ORCHESTRA_URL/index "$user1_auth" ''
#   test_api 200 GET  $ORCHESTRA_URL       "$user2_auth" ''
#   test_api 200 GET  $ORCHESTRA_URL/index "$user2_auth" ''
# }

# api_test_media()
# {
#   pecho 'Test media API'
#   test_api 200 POST   $ORCHESTRA_URL/media               "$user1_auth" "$media1_json"; media1_id=$ID
#   test_api 400 POST   $ORCHESTRA_URL/media               "$user1_auth" "$media1_json"
#   test_api 200 GET    $ORCHESTRA_URL/media/count         "$user2_auth" ''
#   test_api 200 GET    $ORCHESTRA_URL/media               "$user2_auth" ''
#   test_api 403 PATCH  $ORCHESTRA_URL/media/id/$media1_id "$user2_auth" "$media1b_json"
#   test_api 200 PATCH  $ORCHESTRA_URL/media/id/$media1_id "$user1_auth" "$media1b_json"
#   test_api 200 GET    $ORCHESTRA_URL/media/id/$media1_id "$user2_auth" ''
#   test_api 403 DELETE $ORCHESTRA_URL/media/id/$media1_id "$user2_auth" ''
#   test_api 200 DELETE $ORCHESTRA_URL/media/id/$media1_id "$user1_auth" ''
#   test_api 200 POST   $ORCHESTRA_URL/media               "$user1_auth" "$media1_json"; media1_id=$ID
# }

# api_test_tprofile()
# {
#   pecho 'Test transform profile API'
#   mecho 'We cannot double post a profile'
#   test_api 400 POST $ORCHESTRA_URL/transform/profile "$user1_auth" "$tprofile1_json"
#   mecho 'Anonymous can get nothing'
#   test_api 401 GET $ORCHESTRA_URL/transform/profile/count            '' ''
#   test_api 401 GET $ORCHESTRA_URL/transform/profile                  '' ''
#   test_api 401 GET $ORCHESTRA_URL/transform/profile/id/$tprofile1_id '' ''
#   mecho 'Charlie can get nothing'
#   test_api 401 GET $ORCHESTRA_URL/transform/profile/count            "$BAD_AUTH" ''
#   test_api 401 GET $ORCHESTRA_URL/transform/profile                  "$BAD_AUTH" ''
#   test_api 401 GET $ORCHESTRA_URL/transform/profile/id/$tprofile1_id "$BAD_AUTH" ''
#   mecho 'Root can get nothing'
#   test_api 403 GET $ORCHESTRA_URL/transform/profile/count            "$ROOT_AUTH" ''
#   test_api 403 GET $ORCHESTRA_URL/transform/profile                  "$ROOT_AUTH" ''
#   test_api 403 GET $ORCHESTRA_URL/transform/profile/id/$tprofile1_id "$ROOT_AUTH" ''
#   test_api 415 GET $ORCHESTRA_URL/transform/profile/id/salut         "$ROOT_AUTH" ''
#   mecho 'Node can get nothing'
#   test_api 403 GET $ORCHESTRA_URL/transform/profile/count            "$NODE_AUTH" ''
#   test_api 403 GET $ORCHESTRA_URL/transform/profile                  "$NODE_AUTH" ''
#   test_api 403 GET $ORCHESTRA_URL/transform/profile/id/$tprofile1_id "$NODE_AUTH" ''
#   test_api 415 GET $ORCHESTRA_URL/transform/profile/id/salut         "$NODE_AUTH" ''
#   mecho 'Admin can get a lot of things'
#   test_api 200 GET $ORCHESTRA_URL/transform/profile/count            "$user1_auth" ''
#   test_api 200 GET $ORCHESTRA_URL/transform/profile                  "$user1_auth" ''
#   test_api 200 GET $ORCHESTRA_URL/transform/profile/id/$tprofile1_id "$user1_auth" ''
#   test_api 415 GET $ORCHESTRA_URL/transform/profile/id/salut         "$user1_auth" ''
#   mecho 'Simple user can a lot of things'
#   test_api 200 GET $ORCHESTRA_URL/transform/profile/count            "$user2_auth" ''
#   test_api 200 GET $ORCHESTRA_URL/transform/profile                  "$user2_auth" ''
#   test_api 200 GET $ORCHESTRA_URL/transform/profile/id/$tprofile1_id "$user2_auth" ''
#   test_api 415 GET $ORCHESTRA_URL/transform/profile/id/salut         "$user2_auth" ''
# }

# api_test_ttask()
# {
#   pecho 'Test transform task API'
#   #test_api 200 GET  $ORCHESTRA_URL/transform/task/count "$user2_auth" ''
#   #test_api 200 GET  $ORCHESTRA_URL/transform/task       "$user2_auth" ''
#   #test_api 404 POST $ORCHESTRA_URL/transform/task       "$user2_auth" "$ttask0_json"
#   #test_api 404 POST $ORCHESTRA_URL/transform/task       "$user2_auth" "$ttask0b_json"
#   #test_api 404 POST $ORCHESTRA_URL/transform/task       "$user2_auth" "$ttask1_json"
#   #test_api 200 POST $ORCHESTRA_URL/transform/task       "$user2_auth" "$ttask2_json"; ttask2_id=$ID
#   #echo $ttask2_id
#   #test_api 415 GET  $ORCHESTRA_URL/task/transform/1   "$admin" ''
#   #test_api 200 GET  $ORCHESTRA_URL/task/transform/$id "$admin" ''
#   #test_api 400 POST $ORCHESTRA_URL/transform/task     "$user2_auth"  "$tprofile1_json"

#   #while read post_task
#   #do
#   #  [ "$post_task" ] && test_api 0 POST $ORCHESTRA_URL/task/transform "$admin" "$post_task"
#   #done < "$ORCHESTRA_SCRIPTS_PATH/tests.tasks"

#   #test_api 501 PATCH  $ORCHESTRA_URL/task/transform/$id "$admin" ''
#   #test_api 200 DELETE $ORCHESTRA_URL/task/transform/$id "$admin" ''
# }

#!/usr/bin/env python
# -*- coding: utf-8 -*-

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

import os, re, shutil, socket, time
from os.path import abspath, dirname, join
from pytoolbox.encoding import to_bytes
from pytoolbox.filesystem import first_that_exist, try_makedirs
from pytoolbox.juju import  CONFIG_FILENAME, METADATA_FILENAME, DEFAULT_OS_ENV

from .config import StorageLocalConfig
from .constants import LOCAL_CONFIG_FILENAME
from .hooks_base import OsciedCharmHooks


class StorageHooks(OsciedCharmHooks):

    PACKAGES = (u'ntp', u'glusterfs-server', u'nfs-common', u'xfsprogs')

    def __init__(self, metadata, default_config, local_config_filename, default_os_env):
        super(StorageHooks, self).__init__(metadata, default_config, default_os_env, local_config_filename,
                                           StorageLocalConfig)

    # ------------------------------------------------------------------------------------------------------------------

    @property
    def allowed_ips_string(self):
        try:
            allowed_ips = self.config.allowed_ips.split(u',')
        except:
            allowed_ips = [self.config.allowed_ips]
        return u','.join(sorted(list(filter(None, self.local_config.allowed_ips + allowed_ips))))

    def brick(self, address=None):
        address = address or self.private_address
        return u'{0}:{1}/exp{2}'.format(address, self.bricks_path, self.id)

    @property
    def bricks_path(self):
        return join(self.config.bricks_root_path, u'bricks')

    @property
    def volume(self):
        return u'medias_volume_{0}'.format(self.id)

    @property
    def volume_exist(self):
        return self.volume in self.volumes

    @property
    def volumes(self):
        return re.findall(u'Name:\s*(\S*)', self.volume_do(u'info', volume=u'all')[u'stdout'])

    # ------------------------------------------------------------------------------------------------------------------

    def peer_probe(self, peer_address, tries=5):
        # FIXME start if glusterfs-server service not ready <- not implemented, maybe unexpected behavior : needs tests!
        return self.cmd(u'gluster peer probe {0}'.format(peer_address), tries=tries)

    def volume_do(self, action, volume=None, options=u'', tries=5, **kwargs):
        volume = volume or self.volume
        # FIXME start if glusterfs-server service not ready <- not implemented, maybe unexpected behavior : needs tests!
        return self.cmd(u'gluster volume {0} {1} {2}'.format(action, volume, options), tries=tries, **kwargs)

    def volume_create_or_expand(self, volume=None, bricks=None, replica=None):
        # FIXME this implementation do not handle shrinking of a volume, only the expansion
        volume = volume or self.volume
        bricks = bricks or [self.brick()]
        replica = replica or self.config.replica_count
        if len(bricks) < replica:
            self.remark(u'Waiting for {0} peers to create and start a replica={1} volume {2}'.format(
                        replica - len(bricks), replica, volume))
        else:
            if volume in self.volumes:
                vol_bricks = self.volume_infos(volume=volume)[u'bricks']
                self.debug(u'Volume bricks: {0}'.format(vol_bricks))
                new_bricks = [b for b in bricks if b not in vol_bricks]
                new_bricks_count = len(new_bricks)
                # Pick-up the greatest number of new bricks based on number of replica
                new_bricks = new_bricks[:(int(len(new_bricks) / replica) * replica)]
                if len(new_bricks) >= replica:
                    assert len(new_bricks) % replica == 0, u'Number of new bricks is not a multiple of replica'
                    self.info(u'Expand replica={0} volume {1} with new bricks'.format(replica, volume))
                    self.volume_do(u'add-brick', volume=volume, options=u' '.join(new_bricks), fail=False)
                else:
                    self.remark(u'Waiting for {0} peers to expand replica={1} volume {2}'.format(
                                replica - new_bricks_count, replica, volume))
            else:
                # Pick-up the greatest number of bricks based on number of replica
                bricks = bricks[:(int(len(bricks) / replica) * replica)]
                extra = (u' ' if replica == 1 else u' replica {0} transport tcp '.format(replica)) + u' '.join(bricks)
                extra = extra + " force" # Allow volume creation on the root partition
                self.info(u'Create and start a replica={0} volume {1} with {2} brick{3}'.format(
                          replica, volume, len(bricks), u's' if len(bricks) > 1 else u''))
                self.volume_do(u'create', volume=volume, options=extra)
                self.volume_do(u'start', volume=volume)
                self.volume_set_allowed_ips()

    def volume_set_allowed_ips(self, volume=None, tries=5, delay=1.0):
        volume, ips = volume or self.volume, self.allowed_ips_string
        for i in xrange(tries):
            auth_allow = self.volume_infos(volume=volume)[u'auth_allow']
            if auth_allow == ips:
                break
            self.info(u'({0} of {1}) Set volume {2} allowed clients IP list to {3}'.format(i+1, tries, volume, ips))
            self.volume_do(u'set', volume=volume, options=u'auth.allow "{0}"'.format(ips), fail=False, tries=1)
            time.sleep(delay)
        else:
            raise ValueError(to_bytes(u'Volume {0} auth.allow={1} (expected {2})'.format(volume, ips, auth_allow)))
        self.info(self.volume_infos(volume=volume))

    def volume_infos(self, volume=None, tries=5, delay=1.0):
        u"""
        Return a dictionary containing informations about a volume.

        **Example output**::

            {'name': 'medias_volume_6', 'type': 'Distribute', 'status': 'Started',
             'transport': 'tcp', 'bricks': ['domU-12-31-39-06-6C-E9.compute-1.internal:/mnt/bricks/exp6']}
        """
        for i in xrange(tries):
            stdout = self.volume_do(u'info', volume=volume, fail=False)[u'stdout']
            self.debug(u'({0} of {1}) Volume infos stdout: {2}'.format(i+1, tries, repr(stdout)))
            match = self.local_config.volume_infos_regex.match(stdout)
            if match:
                infos = match.groupdict()
                infos[u'bricks'] = re.findall(u'Brick[0-9]+:\s*(\S*)', stdout)
                infos[u'auth_allow'] = u','.join(filter(None, re.findall(u'auth.allow:\s*(\S*)', stdout)))
                return infos
        return None

    # ------------------------------------------------------------------------------------------------------------------

    def hook_install(self):
        cfg = self.config
        self.hook_uninstall()
        self.generate_locales((u'fr_CH.UTF-8',))
        self.install_packages(StorageHooks.PACKAGES)
        self.restart_ntp()
        self.info(u'Configure storage bricks root')
        if cfg.bricks_root_device:
            self.cmd(u'umount {0}'.format(cfg.bricks_root_path), fail=False)
            if cfg.format_bricks_root:
                self.cmd(u'mkfs.xfs {0} -f'.format(cfg.bricks_root_device))  # FIXME detect based on the mount point
            self.cmd(u'mount {0} {1}'.format(cfg.bricks_root_device, cfg.bricks_root_path))  # FIXME add mdadm support?
        try_makedirs(self.bricks_path)
        self.info(u'Expose GlusterFS Server service')
        self.open_port(111,   u'TCP')  # For portmapper, and should have both TCP and UDP open
        self.open_port(111,   u'UDP')
        self.open_port(24007, u'TCP')  # For the Gluster Daemon
        #self.open_port(24008, u'TCP')  # Infiniband management (optional unless you are using IB)
        self.open_port(24009, u'TCP')  # We have only 1 storage brick (24009-24009)
        #self.open_port(38465, u'TCP')  # For NFS (not used)
        #self.open_port(38466, u'TCP')  # For NFS (not used)
        #self.open_port(38467, u'TCP')  # For NFS (not used)

    def hook_config_changed(self):
        if self.volume_exist:
            self.volume_set_allowed_ips()

    def hook_uninstall(self):
        self.info(u'Uninstall prerequisites, remove files & bricks and load default configuration')
        self.hook_stop()
        if self.config.cleanup:
            self.cmd(u'apt-get -y remove --purge {0}'.format(u' '.join(StorageHooks.PACKAGES)))
            self.cmd(u'apt-get -y autoremove')
            shutil.rmtree(u'/etc/glusterd',  ignore_errors=True)
            shutil.rmtree(u'/etc/glusterfs', ignore_errors=True)
        shutil.rmtree(self.bricks_path, ignore_errors=True)
        os.makedirs(self.bricks_path)
        self.local_config.reset()

    def hook_start(self):
        if self.cmd(u'pgrep glusterd', fail=False)[u'returncode'] != 0:
            self.cmd(u'service glusterfs-server start')
        self.start_paya()  # Start paya monitoring (if paya_config_string set in config.yaml)

    def hook_stop(self):
        if self.cmd(u'pgrep glusterd', fail=False)[u'returncode'] == 0:
            self.cmd(u'service glusterfs-server stop')

    def hook_storage_relation_joined(self):
        # Create medias volume if it is already possible to do so
        if self.is_leader:
            self.volume_create_or_expand()
            # Send informations to the requirer only if the volume exist !
            if self.volume_exist:
                self.info(u'Send filesystem (volume {0}) configuration to remote client'.format(self.volume))
                self.relation_set(fstype=u'glusterfs', mountpoint=self.volume, options=u'')
                client_address = socket.getfqdn(self.relation_get('private-address'))
                if not client_address in self.local_config.allowed_ips:
                    self.info(u'Add {0} to allowed clients IPs'.format(client_address))
                    self.local_config.allowed_ips.append(client_address)
                    self.hook_config_changed()

    def hook_storage_relation_departed(self):
        # Get configuration from the relation
        client_address = socket.getfqdn(self.relation_get(u'private-address'))
        if not client_address:
            self.remark(u'Waiting for complete setup')
        elif client_address in self.local_config.allowed_ips:
            self.info(u'Remove {0} from allowed clients IPs'.format(client_address))
            self.local_config.allowed_ips.remove(client_address)
            self.hook_config_changed()

    def hook_peer_relation_joined(self):
        if not self.is_leader and self.volume_exist:
            self.info(u'As slave, stop and delete my own volume {0}'.format(self.volume))
            self.debug(self.volume_infos())
            self.volume_do(u'stop', options=u'force', cli_input=u'y\n')
            self.volume_do(u'delete', cli_input=u'y\n', fail=False)  # FIXME temporary hack

    def hook_peer_relation_changed(self):
        # Get configuration from the relation
        peer_address = socket.getfqdn(self.relation_get(u'private-address'))
        self.info(u'Peer address is {0}'.format(peer_address))
        if not peer_address:
            self.remark(u'Waiting for complete setup')
            return

        # FIXME close previously opened ports if some bricks leaved ...
        self.info(u'Open required ports')
        port, bricks = 24010, [self.brick()]
        for peer in self.relation_list():
            self.open_port(port, u'TCP')  # Open required
            bricks.append(self.brick(socket.getfqdn(self.relation_get(u'private-address', peer))))
            port += 1

        if self.is_leader:
            self.info(u'As leader, probe remote peer {0} and create or expand volume {1}'.format(
                      peer_address, self.volume))
            self.peer_probe(peer_address)
            self.volume_create_or_expand(bricks=bricks)

    def hook_peer_relation_departed(self):
        self.remark(u'FIXME NOT IMPLEMENTED')

# Main -----------------------------------------------------------------------------------------------------------------

if __name__ == u'__main__':
    from pytoolbox.encoding import configure_unicode
    configure_unicode()
    storage_hooks = abspath(join(dirname(__file__), u'../../charms/oscied-storage'))
    StorageHooks(first_that_exist(METADATA_FILENAME,     join(storage_hooks, METADATA_FILENAME)),
                 first_that_exist(CONFIG_FILENAME,       join(storage_hooks, CONFIG_FILENAME)),
                 first_that_exist(LOCAL_CONFIG_FILENAME, join(storage_hooks, LOCAL_CONFIG_FILENAME)),
                 DEFAULT_OS_ENV).trigger()

from __future__ import (absolute_import, division,
                        print_function, unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *

from pysnmp.hlapi import *
from ..interfaces.BackupPower import BackupPower
from ..config import CONFIG_INI

"""Implementation of the White UPS using the BackupPower interface."""


class SnmpUps(BackupPower):

    def get_status(self):

        ip = CONFIG_INI.get(self.config_id, "ip")
        port = CONFIG_INI.getint(self.config_id, "port")
        snmp_oid = CONFIG_INI.get(self.config_id, "snmp_oid")
        community = CONFIG_INI.get(self.config_id, "community")

        """Queries backup power and reports status. Returns whatever format the device uses."""
        for (error_indication,
             error_status,
             error_index,
             var_binds) in getCmd(SnmpEngine(),
                                  CommunityData(community, mpModel=0),
                                  UdpTransportTarget((ip, port)),
                                  ContextData(),
                                  ObjectType(ObjectIdentity(snmp_oid))):
            if error_indication or error_status:
                raise Exception("Error communicating with White UPS.\n" +
                                "Error Indication: " + str(error_indication) + "\n" +
                                "Error Status: " + str(error_status))
            else:
                # The response is a list saved into var_binds, and our OID is listed first.
                return var_binds[0][1]

    def is_shutdown_needed(self):
        """Boolean function to determine whether the system should initiate a shutdown."""
        try:
            return True if self.get_status() != 3 else False
        except Exception as err:
            print(err)
            return True

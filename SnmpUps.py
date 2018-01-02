from __future__ import (absolute_import, division,
                        unicode_literals)

# noinspection PyUnresolvedReferences
from builtins import *
import logging

from pysnmp import hlapi
from ..interfaces.BackupPower import BackupPower
from ..config import CONFIG_INI

"""Implementation of the White UPS using the BackupPower interface."""


class SnmpUps(BackupPower):
    log = logging.getLogger(__name__)

    def get_status(self):

        ip = CONFIG_INI.get(self.config_id, "ip")
        port = CONFIG_INI.getint(self.config_id, "port")
        snmp_oid = CONFIG_INI.get(self.config_id, "snmp_oid")
        community = CONFIG_INI.get(self.config_id, "community")

        """Queries backup power and reports status. Returns whatever format the device uses."""
        for (error_indication,
             error_status,
             error_index,
             var_binds) in hlapi.getCmd(hlapi.SnmpEngine(),
                                        hlapi.CommunityData(community, mpModel=0),
                                        hlapi.UdpTransportTarget((ip, port)),
                                        hlapi.ContextData(),
                                        hlapi.ObjectType(hlapi.ObjectIdentity(snmp_oid))):
            if error_indication or error_status:
                raise Exception("Error communicating with White UPS.\n" +
                                "Error Indication: " + str(error_indication) + "\n" +
                                "Error Status: " + str(error_status))
            else:
                # The response is a list saved into var_binds, and our OID is listed first.
                return var_binds[0][1]

    def is_power_ok(self, return_status_msg=False):
        """Boolean function to determine whether the system should initiate a shutdown."""
        self.log.info("checking SNMP power status")
        try:
            status = self.get_status()
            result = False if status != 3 else True
            if return_status_msg:
                return result, self.__generate_status_message(status)
            else:
                return result

        except Exception as err:
            self.log.exception(err.message)
            if return_status_msg:
                self.log.error("UPS failed safety test: SNMP interface request failed.")
                return False, "UPS failed safety test: SNMP interface request failed."
            else:
                return False

    @staticmethod
    def __generate_status_message(status):
        if status == 3:
            return "UPS passed safety test: A value of 3 was returned over the SNMP interface."
        else:
            return "UPS failed safety test: A value of " + str(status) + " where only 3 is acceptable."

import logging

from pysnmp import hlapi
from catkit.interfaces.BackupPower import BackupPower
from catkit.config import CONFIG_INI

"""Implementation of the UPS using the BackupPower interface."""


class SnmpUps(BackupPower):

    log = logging.getLogger(__name__)

    def __init__(self, config_id):
        self.config_id = config_id
        self.ip = CONFIG_INI.get(self.config_id, "ip")
        self.port = CONFIG_INI.getint(self.config_id, "port")
        self.snmp_oid = CONFIG_INI.get(self.config_id, "snmp_oid")
        self.community = CONFIG_INI.get(self.config_id, "community")
        self.pass_status = CONFIG_INI.getint(self.config_id, "pass_status")

    def get_status(self):
        """Queries backup power and reports status. Returns whatever format the device uses."""
        for (error_indication,
             error_status,
             error_index,
             var_binds) in hlapi.getCmd(hlapi.SnmpEngine(),
                                        hlapi.CommunityData(self.community, mpModel=0),
                                        hlapi.UdpTransportTarget((self.ip, self.port)),
                                        hlapi.ContextData(),
                                        hlapi.ObjectType(hlapi.ObjectIdentity(self.snmp_oid))):
            if error_indication or error_status:
                raise Exception(f"Error communicating with the UPS: '{self.config_id}'.\n" +
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
            result = status == self.pass_status
            if return_status_msg:
                return result, self._generate_status_message(status)
            else:
                return result

        except Exception as err:
            self.log.exception(err.message)
            if return_status_msg:
                error_message = f"{self.config_id} failed safety test: SNMP interface request failed."
                self.log.error(error_message)
                return False, error_message
            else:
                return False

    def _generate_status_message(self, status):
        if status == self.pass_status:
            return f"{self.config_id} passed safety test: A value of {status} was returned over the SNMP interface."
        else:
            return f"{self.config_id} failed safety test: A value of {status} where only {self.pass_status} is acceptable."

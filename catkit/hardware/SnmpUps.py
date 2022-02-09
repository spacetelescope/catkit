import logging

from pysnmp import hlapi
from catkit.interfaces.BackupPower import BackupPower

"""Implementation of the UPS using the BackupPower interface."""


class SnmpUps(BackupPower):

    log = logging.getLogger()

    def __init__(self, config_id, ip, snmp_oid, pass_status, port=161, community="public"):
        self.config_id = config_id
        self.ip = ip
        self.snmp_oid = snmp_oid
        self.pass_status = pass_status
        self.port = port
        self.community = community

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
        self.log.info(f"checking {self.config_id} SNMP power status")
        try:
            status = self.get_status()
            result = status == self.pass_status
            if return_status_msg:
                return result, self._generate_status_message(status)
            else:
                return result

        except Exception:
            error_message = f"{self.config_id} SNMP interface request failed."
            self.log.exception(error_message)
            if return_status_msg:
                return False, error_message
            else:
                return False

    def _generate_status_message(self, status):
        if status == self.pass_status:
            return f"{self.config_id} passed safety test: A value of {status} was returned over the SNMP interface."
        else:
            return f"{self.config_id} failed safety test: A value of {status} where only {self.pass_status} is acceptable."

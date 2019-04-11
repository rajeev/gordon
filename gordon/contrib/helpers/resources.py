import six

from gordon.utils import BaseLambdaAWSCustomObject


class Sleep(BaseLambdaAWSCustomObject):
    """CloudFormation Custom resource which waits ``Time`` seconds before
    succeeding."""

    resource_type = "Custom::Sleep"
    props = {
        'ServiceToken': (six.string_types, True),
        'Time': (int, True)
    }

class MaintenanceModeOn(BaseLambdaAWSCustomObject):
    """Custom Resource that sets MaintenanceModeOn"""

    resource_type = "Custom::MaintenanceModeOn"
    props = {
        'ServiceToken': (six.string_types, True),
        'Timestamp': (int, True)
    }


class MaintenanceModeOff(BaseLambdaAWSCustomObject):
    """Custom Resource that sets MaintenanceModeOff"""

    resource_type = "Custom::MaintenanceModeOff"
    props = {
        'ServiceToken': (six.string_types, True),
        'Timestamp': (int, True)
    }

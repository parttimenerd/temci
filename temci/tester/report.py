from .rundata import RunDataStatsHelper
from ..utils.typecheck import *
from ..utils.registry import AbstractRegistry, register

class ReporterRegistry(AbstractRegistry):

    def __init__(self):
        super().__init__(["report"], use_key="reporter", use_list=False, default="console")

class AbstractReporter:
    pass
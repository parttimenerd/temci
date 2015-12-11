from temci.utils.typecheck import *
from temci.tester.report import ReporterRegistry
from temci.tester.rundata import RunDataStatsHelper

class ReportProcessor:

    def __init__(self, stats_helper: RunDataStatsHelper = None):
        self.reporter = ReporterRegistry.get_for_name(ReporterRegistry.get_used(), stats_helper)

    def report(self):
        self.reporter.report()
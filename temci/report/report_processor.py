from temci.report.report import ReporterRegistry, AbstractReporter
from temci.report.rundata import RunDataStatsHelper

class ReportProcessor:
    """
    Simplifies the work with reporters.
    """

    def __init__(self, stats_helper: RunDataStatsHelper = None):
        """
        Creates an instance.

        :param stats_helper: used data wrapper or None if an empty one should be used
        """
        used = ReporterRegistry.get_used()
        self.reporter = ReporterRegistry.get_for_name(used, stats_helper)  # type: AbstractReporter
        """ Used reporter """

    def report(self):
        """ Create a report with the used reporter """
        self.reporter.report()
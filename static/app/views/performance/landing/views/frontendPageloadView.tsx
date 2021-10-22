import {usePageError} from 'app/utils/performance/contexts/pageError';

import Table from '../../table';
import {FRONTEND_PAGELOAD_COLUMN_TITLES} from '../data';
import {TripleChartRow} from '../widgets/components/widgetChartRow';
import {PerformanceWidgetSetting} from '../widgets/widgetDefinitions';

import {BasePerformanceViewProps} from './types';

export function FrontendPageloadView(props: BasePerformanceViewProps) {
  return (
    <div data-test-id="frontend-pageload-view">
      <TripleChartRow
        {...props}
        allowedCharts={[
          PerformanceWidgetSetting.P75_LCP_AREA,
          PerformanceWidgetSetting.LCP_HISTOGRAM,
          PerformanceWidgetSetting.FCP_HISTOGRAM,
          PerformanceWidgetSetting.USER_MISERY_AREA,
          PerformanceWidgetSetting.TPM_AREA,
        ]}
      />
      <Table
        {...props}
        columnTitles={FRONTEND_PAGELOAD_COLUMN_TITLES}
        setError={usePageError().setPageError}
      />
    </div>
  );
}

import { SNMPChartConfig } from './snmpModuleRegistry';
import GlassCard from '../../../components/GlassCard';
import SNMPMetricChart from '../components/SNMPMetricChart';

interface SNMPModuleChartProps {
  config: SNMPChartConfig;
  data: Array<{ timestamp: string; [key: string]: any }>;
  title?: string;
  subtitle?: string;
  height?: number;
  className?: string;
  showCurrentValue?: boolean;
  currentValue?: number | null;
  currentValueLabel?: string;
}

export default function SNMPModuleChart({
  config,
  data,
  title,
  subtitle,
  height,
  className = '',
  showCurrentValue = true,
  currentValue,
  currentValueLabel,
}: SNMPModuleChartProps) {
  const chartHeight = height || config.height || 200;
  const chartData = data.map((point) => ({
    timestamp: point.timestamp,
    value: point[config.valueKey],
  }));

  return (
    <GlassCard className={`p-4 ${className}`}>
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="font-display font-bold text-sm tracking-wider neon-cyan">
            {title || config.label}
          </div>
          {subtitle && (
            <div className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
              {subtitle}
            </div>
          )}
        </div>
        {showCurrentValue && currentValue !== undefined && currentValue !== null && (
          <div className="font-mono text-xs px-2 py-1 rounded" style={{ color: config.color, background: `rgba(${config.color.replace('#', '')}, 0.1)`, border: `1px solid ${config.color}40` }}>
            {currentValueLabel || config.label}: {currentValue.toFixed(1)}{config.unit}
          </div>
        )}
      </div>
      <SNMPMetricChart
        data={chartData}
        height={chartHeight}
        color={config.color}
        unit={config.unit}
        label={config.label}
        showArea={config.showArea ?? true}
        showGrid={true}
        showAxes={true}
        noDataMessage="No Historical Data Yet"
      />
    </GlassCard>
  );
}

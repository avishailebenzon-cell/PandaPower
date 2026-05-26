import React, { ReactNode } from "react";

export interface AnalyticsChartProps {
  title?: string; // Hebrew title
  children: ReactNode; // Recharts chart component
  height?: number; // Chart height in pixels (default: 400)
  width?: number | string; // Chart width (default: 100%)
}

/**
 * Wrapper component for analytics charts with RTL support and consistent styling.
 * Intended to be used with Recharts components (LineChart, BarChart, FunnelChart, etc.)
 */
const AnalyticsChart: React.FC<AnalyticsChartProps> = ({
  title,
  children,
  height = 400,
  width = "100%",
}) => {
  return (
    <div dir="rtl" className="bg-gray-800 rounded-lg border border-gray-700 p-4">
      {title && (
        <h3 className="text-lg font-semibold text-white text-right mb-4">
          {title}
        </h3>
      )}

      <div className="overflow-x-auto" style={{ width }}>
        <div style={{ height, width: width === "100%" ? "100%" : width }}>
          {children}
        </div>
      </div>
    </div>
  );
};

export default AnalyticsChart;

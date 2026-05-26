import React from "react";

export interface KPICardProps {
  label: string; // Hebrew label
  value: number | string;
  metric?: string; // Optional unit/description
  color: string; // Tailwind color class (e.g., 'bg-green-900')
  trend?: {
    value: number; // Percentage change
    direction: "up" | "down"; // "up" or "down"
  };
  size?: "sm" | "md" | "lg"; // Card size
}

const KPICard: React.FC<KPICardProps> = ({
  label,
  value,
  metric,
  color,
  trend,
  size = "md",
}) => {
  // Size classes
  const sizeClasses = {
    sm: "p-3",
    md: "p-4",
    lg: "p-6",
  };

  const valueSizeClasses = {
    sm: "text-2xl",
    md: "text-4xl",
    lg: "text-5xl",
  };

  const labelSizeClasses = {
    sm: "text-sm",
    md: "text-base",
    lg: "text-lg",
  };

  // Format value for display
  const displayValue = typeof value === "number"
    ? value.toLocaleString("he-IL", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 1
      })
    : value;

  return (
    <div className={`${color} rounded-lg border border-gray-600 ${sizeClasses[size]} hover:border-gray-500 transition-colors`}>
      {/* Label */}
      <p className={`text-gray-300 font-medium text-right ${labelSizeClasses[size]}`}>
        {label}
      </p>

      {/* Value */}
      <div className="flex items-end justify-between gap-3 mt-3">
        <div className="flex-1">
          <p className={`text-white font-bold text-right ${valueSizeClasses[size]}`}>
            {displayValue}
          </p>
          {metric && (
            <p className="text-xs text-gray-400 text-right mt-1">{metric}</p>
          )}
        </div>

        {/* Trend Indicator */}
        {trend && (
          <div className={`text-right ${trend.direction === "up" ? "text-green-400" : "text-red-400"}`}>
            <div className="text-lg font-bold">
              {trend.direction === "up" ? "↑" : "↓"}
            </div>
            <div className="text-xs">{Math.abs(trend.value)}%</div>
          </div>
        )}
      </div>
    </div>
  );
};

export default KPICard;

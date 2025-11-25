import React, { useState, useEffect } from "react";
import { formatDistanceToNow } from "date-fns";

interface RelativeTimeProps {
  date: string | Date;
  suffix?: boolean;
  updateInterval?: number; // milliseconds
}

/**
 * Displays timestamp as relative time (e.g., "2 hours ago")
 * Auto-updates every minute by default
 */
export function RelativeTime({
  date,
  suffix = true,
  updateInterval = 60000,
}: RelativeTimeProps) {
  const [time, setTime] = useState(() =>
    formatDistanceToNow(new Date(date), { addSuffix: suffix })
  );

  useEffect(() => {
    // Update time display on interval
    const interval = setInterval(() => {
      setTime(formatDistanceToNow(new Date(date), { addSuffix: suffix }));
    }, updateInterval);

    return () => clearInterval(interval);
  }, [date, suffix, updateInterval]);

  // Show full timestamp on hover
  const fullTimestamp = new Date(date).toLocaleString();

  return <span title={fullTimestamp}>{time}</span>;
}

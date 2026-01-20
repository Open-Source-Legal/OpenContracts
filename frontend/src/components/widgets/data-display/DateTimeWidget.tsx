import { StatBlock } from "@os-legal/ui";

export function DateTimeWidget({
  timeString,
  dateString,
}: {
  timeString: string;
  dateString: string;
}) {
  return <StatBlock value={timeString} label={dateString} size="sm" />;
}

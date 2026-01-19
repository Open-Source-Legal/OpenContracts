import { Statistic } from "semantic-ui-react";
import { Share2, Lock, Pencil, ShieldOff } from "lucide-react";
import { getPermissions } from "../../../utils/transform";
import { PermissionTypes } from "../../types";

export const MyPermissionsIndicator = ({
  myPermissions,
  isPublic,
}: {
  myPermissions: string[] | undefined;
  isPublic: boolean | undefined;
}) => {
  const perms = getPermissions(myPermissions);
  let stats: React.ReactNode[] = [];

  if (isPublic) {
    stats.push(
      <Statistic key={`stat_${stats.length}`}>
        <Statistic.Value>
          <Share2 size={24} color="#21ba45" />
        </Statistic.Value>
        <Statistic.Label>Public</Statistic.Label>
      </Statistic>
    );
  } else {
    stats.push(
      <Statistic key={`stat_${stats.length}`}>
        <Statistic.Value>
          <ShieldOff size={24} color="#a5673f" />
        </Statistic.Value>
        <Statistic.Label>Private</Statistic.Label>
      </Statistic>
    );
  }

  if (perms.includes(PermissionTypes.CAN_UPDATE)) {
    stats.push(
      <Statistic key={`stat_${stats.length}`}>
        <Statistic.Value>
          <Pencil size={24} color="#21ba45" />
        </Statistic.Value>
        <Statistic.Label>Can Edit</Statistic.Label>
      </Statistic>
    );
  } else {
    stats.push(
      <Statistic key={`stat_${stats.length}`}>
        <Statistic.Value>
          <Lock size={24} color="#db2828" />
        </Statistic.Value>
        <Statistic.Label>Read Only</Statistic.Label>
      </Statistic>
    );
  }

  return <>{stats}</>;
};

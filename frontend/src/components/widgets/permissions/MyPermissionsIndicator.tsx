import { StatBlock } from "@os-legal/ui";
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
      <StatBlock
        key={`stat_${stats.length}`}
        value=""
        label="Public"
        icon={<Share2 size={24} color="#21ba45" />}
        size="sm"
      />
    );
  } else {
    stats.push(
      <StatBlock
        key={`stat_${stats.length}`}
        value=""
        label="Private"
        icon={<ShieldOff size={24} color="#a5673f" />}
        size="sm"
      />
    );
  }

  if (perms.includes(PermissionTypes.CAN_UPDATE)) {
    stats.push(
      <StatBlock
        key={`stat_${stats.length}`}
        value=""
        label="Can Edit"
        icon={<Pencil size={24} color="#21ba45" />}
        size="sm"
      />
    );
  } else {
    stats.push(
      <StatBlock
        key={`stat_${stats.length}`}
        value=""
        label="Read Only"
        icon={<Lock size={24} color="#db2828" />}
        size="sm"
      />
    );
  }

  return <>{stats}</>;
};

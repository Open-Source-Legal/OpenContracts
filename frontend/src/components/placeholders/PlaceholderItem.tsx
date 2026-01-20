import { Item } from "semantic-ui-react";
import { Skeleton, SkeletonText } from "@os-legal/ui";

interface PlaceholderItemProps {
  title?: string;
  subtitle?: string;
  description?: string;
  image_src?: string;
}

export const PlaceholderItem = ({
  title,
  subtitle,
  description,
  image_src,
}: PlaceholderItemProps) => {
  return (
    <Item>
      {image_src ? (
        <Item.Image size="tiny" src={image_src} />
      ) : (
        <Skeleton variant="rectangular" width={80} height={80} />
      )}

      <Item.Content>
        <Item.Header>
          {title ? title : <Skeleton variant="text" width="60%" />}
        </Item.Header>
        <Item.Meta>
          {subtitle ? (
            <span>{subtitle}</span>
          ) : (
            <Skeleton variant="text" width="40%" />
          )}
        </Item.Meta>
        <Item.Description>
          {description ? description : <SkeletonText lines={3} />}
        </Item.Description>
      </Item.Content>
    </Item>
  );
};

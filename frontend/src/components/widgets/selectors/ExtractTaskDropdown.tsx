import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Dropdown, DropdownProps } from "semantic-ui-react";
import { useQuery } from "@apollo/client";
import _ from "lodash";
import {
  GET_REGISTERED_EXTRACT_TASKS,
  GetRegisteredExtractTasksOutput,
} from "../../../graphql/queries";
import styled from "styled-components";

interface ExtractTaskDropdownProps {
  read_only?: boolean;
  taskName?: string | undefined;
  style?: React.CSSProperties;
  onChange?: (taskName: string | null) => void;
}

const StyledDropdown = styled(Dropdown)`
  &.ui.dropdown {
    width: 100%; // Remove the hardcoded minWidth

    // Handle long text in the selected value
    .text {
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 100%;
    }

    // Style the dropdown menu
    .menu {
      width: max-content; // Allow menu to be wider than the dropdown
      min-width: 100%; // But at least as wide as the dropdown
      max-width: 80vw; // Prevent extremely wide menus

      // Style the menu items
      > .item {
        .header {
          white-space: normal;
          word-break: break-word;
          font-size: 0.9em;
          margin-bottom: 0.2em;
        }

        .sub.header {
          white-space: normal;
          word-break: break-word;
          font-size: 0.8em;
          color: rgba(0, 0, 0, 0.6);
          line-height: 1.3;
        }
      }
    }
  }
`;

const DropdownOptionHeader = styled.div`
  font-weight: 600;
  font-size: 0.9em;
  color: #1e293b;
  margin-bottom: 0.2em;
  white-space: normal;
  word-break: break-word;
`;

const DropdownOptionSubheader = styled.div`
  font-size: 0.8em;
  color: rgba(0, 0, 0, 0.6);
  font-weight: 400;
  white-space: normal;
  word-break: break-word;
  line-height: 1.3;
`;

export const ExtractTaskDropdown: React.FC<ExtractTaskDropdownProps> = ({
  read_only,
  style,
  onChange,
  taskName,
}) => {
  const [searchQuery, setSearchQuery] = useState<string>();

  const { loading, error, data, refetch } =
    useQuery<GetRegisteredExtractTasksOutput>(GET_REGISTERED_EXTRACT_TASKS, {
      fetchPolicy: "network-only",
      notifyOnNetworkStatusChange: true,
    });

  useEffect(() => {
    refetch();
  }, [searchQuery]);

  const tasks = useMemo(() => {
    if (!data) return [];
    return Object.entries(data.registeredExtractTasks).map(
      ([name, description]) => ({
        name,
        description: description as string,
      })
    );
  }, [data]);

  const debouncedSetSearchQuery = useCallback(
    _.debounce((query: string) => {
      setSearchQuery(query);
    }, 500),
    []
  );

  const handleSearchChange = (
    event: React.SyntheticEvent<HTMLElement>,
    { searchQuery }: { searchQuery: string }
  ) => {
    debouncedSetSearchQuery(searchQuery);
  };

  const handleSelectionChange = (
    event: React.SyntheticEvent<HTMLElement>,
    data: DropdownProps
  ) => {
    if (onChange) {
      const selected = _.find(tasks, { name: data.value as string });
      onChange(selected ? selected.name : null);
    }
  };

  // Memoize options to prevent unnecessary recalculations
  const dropdownOptions = useMemo(
    () =>
      tasks.map((task) => ({
        key: task.name,
        text: task.name,
        value: task.name,
        content: (
          <div>
            <DropdownOptionHeader>{task.name}</DropdownOptionHeader>
            <DropdownOptionSubheader>
              {task.description}
            </DropdownOptionSubheader>
          </div>
        ),
      })),
    [tasks]
  );

  if (error) {
    return <div>Error: {error.message}</div>;
  }

  return (
    <StyledDropdown
      fluid
      selection
      search
      disabled={read_only}
      options={dropdownOptions} // Use memoized options
      value={taskName}
      placeholder="Select a task"
      onChange={read_only ? () => {} : handleSelectionChange}
      onSearchChange={handleSearchChange}
      loading={loading}
      style={style}
    />
  );
};

import React from "react";
import { MockedProvider } from "@apollo/client/testing";

interface MCPShareButtonTestWrapperProps {
  children: React.ReactNode;
}

export function MCPShareButtonTestWrapper({
  children,
}: MCPShareButtonTestWrapperProps) {
  return (
    <MockedProvider mocks={[]} addTypename={false}>
      {children}
    </MockedProvider>
  );
}

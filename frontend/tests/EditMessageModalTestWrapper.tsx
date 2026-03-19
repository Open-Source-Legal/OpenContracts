import React from "react";
import { MockedProvider, MockedResponse } from "@apollo/client/testing";
import { EditMessageModal } from "../src/components/threads/EditMessageModal";

interface WrapperProps {
  isOpen: boolean;
  initialContent: string;
  messageId: string;
  mocks?: MockedResponse[];
  onClose?: () => void;
  onSuccess?: () => void;
}

export const EditMessageModalTestWrapper: React.FC<WrapperProps> = ({
  isOpen,
  initialContent,
  messageId,
  mocks = [],
  onClose = () => {},
  onSuccess,
}) => (
  <MockedProvider mocks={mocks} addTypename={false}>
    <EditMessageModal
      isOpen={isOpen}
      onClose={onClose}
      messageId={messageId}
      initialContent={initialContent}
      onSuccess={onSuccess}
    />
  </MockedProvider>
);

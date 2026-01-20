import React, { useEffect, useMemo, useState } from "react";
import { Modal } from "semantic-ui-react";
import { useMutation, useReactiveVar } from "@apollo/client";
import { UserCircle, X, Check } from "lucide-react";
import { Button, Input, FormField, Toggle } from "@os-legal/ui";
import styled from "styled-components";

import { backendUserObj, showUserSettingsModal } from "../../graphql/cache";
import {
  UPDATE_ME,
  UpdateMeInputs,
  UpdateMeOutputs,
} from "../../graphql/mutations";
import { UserBadges } from "../badges/UserBadges";

const StyledModal = styled(Modal)`
  &.ui.modal {
    @media (max-width: 768px) {
      width: 95% !important;
      margin: 0.5rem auto !important;
    }

    > .header {
      @media (max-width: 768px) {
        padding: 1rem !important;
        font-size: 1.1rem !important;

        .sub.header {
          font-size: 0.85rem !important;
          margin-top: 0.25rem !important;
        }
      }
    }

    > .content {
      @media (max-width: 768px) {
        padding: 1rem !important;
      }
    }

    > .actions {
      @media (max-width: 768px) {
        padding: 0.75rem 1rem !important;
        display: flex;
        flex-direction: column-reverse;
        gap: 0.5rem;

        .button {
          margin: 0 !important;
          width: 100%;
        }
      }
    }
  }
`;

const ResponsiveFormGroup = styled.div`
  display: flex;
  gap: 1rem;

  @media (max-width: 480px) {
    flex-direction: column;

    > * {
      width: 100%;
      margin-bottom: 1em;

      &:last-child {
        margin-bottom: 0;
      }
    }
  }

  > * {
    flex: 1;
  }
`;

const ProfileVisibilityHint = styled.div`
  font-size: 12px;
  color: #666;
  margin-top: 0.5rem;

  @media (max-width: 768px) {
    font-size: 11px;
  }
`;

const ModalHeaderWrapper = styled.div`
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 1.5rem;
  background: white;
  border-bottom: 1px solid #e2e8f0;
`;

const ModalHeaderTitle = styled.h2`
  font-size: 1.5rem;
  font-weight: 600;
  color: #1e293b;
  margin: 0.5rem 0 0 0;
`;

const ModalHeaderSubtitle = styled.span`
  font-size: 0.875rem;
  color: #64748b;
  margin-top: 0.25rem;
`;

const StyledDivider = styled.hr`
  border: none;
  border-top: 1px solid rgba(34, 36, 38, 0.15);
  margin: 1.5rem 0;
`;

interface EditableProfileState {
  name?: string;
  firstName?: string;
  lastName?: string;
  phone?: string;
  slug?: string;
  isProfilePublic?: boolean; // Issue #611
}

const UserSettingsModal: React.FC = () => {
  const isOpen = useReactiveVar(showUserSettingsModal);
  const user = useReactiveVar(backendUserObj);
  const [form, setForm] = useState<EditableProfileState>({});
  const [dirty, setDirty] = useState<boolean>(false);

  useEffect(() => {
    if (user) {
      setForm({
        name: (user as any).name,
        firstName: (user as any).firstName,
        lastName: (user as any).lastName,
        phone: (user as any).phone,
        slug: (user as any).slug,
        isProfilePublic: (user as any).isProfilePublic ?? true, // Issue #611
      });
      setDirty(false);
    }
  }, [user, isOpen]);

  const [updateMe, { loading }] = useMutation<UpdateMeOutputs, UpdateMeInputs>(
    UPDATE_ME,
    {
      onCompleted: (data) => {
        if (data.updateMe?.user) {
          backendUserObj({ ...(user as any), ...data.updateMe.user });
        }
        showUserSettingsModal(false);
      },
    }
  );

  const onChange = (key: keyof EditableProfileState, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setDirty(true);
  };

  const canSave = useMemo(() => dirty && !!user, [dirty, user]);

  return (
    <StyledModal
      open={isOpen}
      onClose={() => showUserSettingsModal(false)}
      size="small"
      closeIcon
      data-testid="user-settings-modal"
    >
      <ModalHeaderWrapper data-testid="user-settings-header">
        <UserCircle size={32} />
        <ModalHeaderTitle>User Settings</ModalHeaderTitle>
        <ModalHeaderSubtitle>
          Update your profile and public slug
        </ModalHeaderSubtitle>
      </ModalHeaderWrapper>
      <Modal.Content>
        <form>
          <Input
            label="Public Slug"
            placeholder="your-slug"
            value={form.slug || ""}
            onChange={(e) => onChange("slug", e.target.value)}
            fullWidth
          />
          <Input
            label="Name"
            placeholder="Display name"
            value={form.name || ""}
            onChange={(e) => onChange("name", e.target.value)}
            fullWidth
          />
          <ResponsiveFormGroup>
            <Input
              label="First Name"
              value={form.firstName || ""}
              onChange={(e) => onChange("firstName", e.target.value)}
              fullWidth
            />
            <Input
              label="Last Name"
              value={form.lastName || ""}
              onChange={(e) => onChange("lastName", e.target.value)}
              fullWidth
            />
          </ResponsiveFormGroup>
          <Input
            label="Phone"
            value={form.phone || ""}
            onChange={(e) => onChange("phone", e.target.value)}
            fullWidth
          />
          <FormField label="Profile Visibility">
            <Toggle
              label="Public Profile"
              checked={form.isProfilePublic ?? true}
              onChange={(e) => {
                setForm((prev) => ({
                  ...prev,
                  isProfilePublic: e.target.checked,
                }));
                setDirty(true);
              }}
            />
            <ProfileVisibilityHint>
              {form.isProfilePublic
                ? "Your profile is visible to all users"
                : "Your profile is only visible to you"}
            </ProfileVisibilityHint>
          </FormField>
        </form>

        {user && (user as any).id && (
          <>
            <StyledDivider />
            <UserBadges
              userId={(user as any).id}
              showTitle={true}
              title="Your Badges"
            />
          </>
        )}
      </Modal.Content>
      <Modal.Actions>
        <Button
          variant="ghost"
          onClick={() => showUserSettingsModal(false)}
          disabled={loading}
          leftIcon={<X size={16} />}
        >
          Close
        </Button>
        <Button
          variant="primary"
          disabled={!canSave}
          loading={loading}
          onClick={() => updateMe({ variables: form })}
          leftIcon={<Check size={16} />}
        >
          Save
        </Button>
      </Modal.Actions>
    </StyledModal>
  );
};

export default UserSettingsModal;

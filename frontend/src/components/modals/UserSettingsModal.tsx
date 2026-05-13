import React, { useEffect, useMemo, useState } from "react";
import {
  Modal,
  ModalHeader,
  ModalBody,
  ModalFooter,
  Button,
  Input,
} from "@os-legal/ui";
import { useMutation, useReactiveVar } from "@apollo/client";
import styled from "styled-components";
import { UserCircle, X, Check } from "lucide-react";

import { backendUserObj, showUserSettingsModal } from "../../graphql/cache";
import {
  OS_LEGAL_COLORS,
  accentAlpha,
} from "../../assets/configurations/osLegalStyles";
import {
  UPDATE_ME,
  UpdateMeInputs,
  UpdateMeOutputs,
} from "../../graphql/mutations";
import { UserBadges } from "../badges/UserBadges";

const ResponsiveFormGroup = styled.div`
  display: flex;
  gap: 1rem;

  @media (max-width: 480px) {
    flex-direction: column;
    gap: 0;
  }

  > div {
    flex: 1;
  }
`;

const ProfileVisibilityHint = styled.div`
  font-size: 12px;
  color: ${OS_LEGAL_COLORS.textSecondary};
  margin-top: 0.5rem;

  @media (max-width: 768px) {
    font-size: 11px;
  }
`;

const FormField = styled.div`
  margin-bottom: 1rem;

  label {
    display: block;
    font-weight: 600;
    font-size: 0.875rem;
    margin-bottom: 0.375rem;
    color: ${OS_LEGAL_COLORS.textPrimary};
  }
`;

const MarkdownTextarea = styled.textarea`
  width: 100%;
  padding: 0.5rem;
  resize: vertical;
  font-family: inherit;
  font-size: 0.875rem;
  color: ${OS_LEGAL_COLORS.textPrimary};
  background: ${OS_LEGAL_COLORS.surface};
  border: 1px solid ${OS_LEGAL_COLORS.border};
  border-radius: 6px;
  /* WCAG 2.4.7 Focus Visible — combine border-color with a 2px box-shadow
   * focus ring so the indicator survives high-contrast / forced-colors mode
   * where a single border-color shift can be invisible. */
  transition: border-color 120ms ease, box-shadow 120ms ease;

  &:focus,
  &:focus-visible {
    outline: none;
    border-color: ${OS_LEGAL_COLORS.accent};
    box-shadow: 0 0 0 2px ${accentAlpha(0.35)};
  }
`;

interface EditableProfileState {
  name?: string;
  firstName?: string;
  lastName?: string;
  phone?: string;
  slug?: string;
  isProfilePublic?: boolean; // Issue #611
  profileHeadline?: string;
  profileAboutMarkdown?: string;
  profileLinksMarkdown?: string;
}

const UserSettingsModal: React.FC = () => {
  const isOpen = useReactiveVar(showUserSettingsModal);
  const user = useReactiveVar(backendUserObj);
  const [form, setForm] = useState<EditableProfileState>({});
  const [dirty, setDirty] = useState<boolean>(false);

  useEffect(() => {
    if (user) {
      const u = user as Partial<EditableProfileState>;
      setForm({
        name: u.name,
        firstName: u.firstName,
        lastName: u.lastName,
        phone: u.phone,
        slug: u.slug,
        isProfilePublic: u.isProfilePublic ?? true, // Issue #611
        profileHeadline: u.profileHeadline ?? "",
        profileAboutMarkdown: u.profileAboutMarkdown ?? "",
        profileLinksMarkdown: u.profileLinksMarkdown ?? "",
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
    <Modal
      open={isOpen}
      onClose={() => showUserSettingsModal(false)}
      data-testid="user-settings-modal"
    >
      <ModalHeader>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <UserCircle size={24} />
          <div>
            <div>User Settings</div>
            <div
              style={{
                fontSize: "0.85rem",
                fontWeight: 400,
                color: OS_LEGAL_COLORS.textSecondary,
              }}
            >
              Update your profile and public slug
            </div>
          </div>
        </div>
      </ModalHeader>
      <ModalBody>
        <form onSubmit={(e) => e.preventDefault()}>
          <Input
            label="Public Slug"
            placeholder="your-slug"
            fullWidth
            value={form.slug || ""}
            onChange={(e) => onChange("slug", e.target.value)}
          />
          <div style={{ height: "1rem" }} />
          <Input
            label="Name"
            placeholder="Display name"
            fullWidth
            value={form.name || ""}
            onChange={(e) => onChange("name", e.target.value)}
          />
          <div style={{ height: "1rem" }} />
          <ResponsiveFormGroup>
            <div>
              <Input
                label="First Name"
                fullWidth
                value={form.firstName || ""}
                onChange={(e) => onChange("firstName", e.target.value)}
              />
            </div>
            <div>
              <Input
                label="Last Name"
                fullWidth
                value={form.lastName || ""}
                onChange={(e) => onChange("lastName", e.target.value)}
              />
            </div>
          </ResponsiveFormGroup>
          <div style={{ height: "1rem" }} />
          <Input
            label="Phone"
            fullWidth
            value={form.phone || ""}
            onChange={(e) => onChange("phone", e.target.value)}
          />
          <div style={{ height: "1rem" }} />
          <Input
            label="Profile Headline"
            fullWidth
            placeholder="What do you do? (e.g. Contracts counsel + legal ops)"
            value={form.profileHeadline || ""}
            maxLength={200}
            onChange={(e) => onChange("profileHeadline", e.target.value)}
          />
          <div style={{ height: "1rem" }} />
          <FormField>
            <label htmlFor="profile-about-markdown">About (Markdown)</label>
            <MarkdownTextarea
              id="profile-about-markdown"
              rows={6}
              value={form.profileAboutMarkdown || ""}
              maxLength={5000}
              onChange={(e) => onChange("profileAboutMarkdown", e.target.value)}
              placeholder="Write a short bio in Markdown"
            />
          </FormField>
          <FormField>
            <label htmlFor="profile-links-markdown">Links (Markdown)</label>
            <MarkdownTextarea
              id="profile-links-markdown"
              rows={4}
              value={form.profileLinksMarkdown || ""}
              maxLength={5000}
              onChange={(e) => onChange("profileLinksMarkdown", e.target.value)}
              placeholder="- [Website](https://example.com)"
            />
          </FormField>
          <FormField>
            <label>Profile Visibility</label>
            <label
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                cursor: "pointer",
                fontWeight: 400,
              }}
            >
              <input
                type="checkbox"
                checked={form.isProfilePublic ?? true}
                onChange={(e) => {
                  setForm((prev) => ({
                    ...prev,
                    isProfilePublic: e.target.checked,
                  }));
                  setDirty(true);
                }}
              />
              Public Profile
            </label>
            <ProfileVisibilityHint>
              {form.isProfilePublic
                ? "Your profile is visible to all users"
                : "Your profile is only visible to you"}
            </ProfileVisibilityHint>
          </FormField>
        </form>

        {user && (user as any).id && (
          <>
            <hr
              style={{
                border: "none",
                borderTop: `1px solid ${OS_LEGAL_COLORS.border}`,
                margin: "1.5rem 0",
              }}
            />
            <UserBadges
              userId={(user as any).id}
              showTitle={true}
              title="Your Badges"
            />
          </>
        )}
      </ModalBody>
      <ModalFooter>
        <Button
          variant="secondary"
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
      </ModalFooter>
    </Modal>
  );
};

export default UserSettingsModal;

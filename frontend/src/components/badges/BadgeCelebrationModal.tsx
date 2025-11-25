import React, { useEffect, useState } from "react";
import styled from "styled-components";
import { motion, AnimatePresence } from "framer-motion";
import * as LucideIcons from "lucide-react";
import { Sparkles, X } from "lucide-react";
import { color } from "../../theme/colors";
import { spacing } from "../../theme/spacing";

const Overlay = styled(motion.div)`
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10000;
  backdrop-filter: blur(4px);
`;

const ModalContainer = styled(motion.div)`
  background: ${color.N1};
  border-radius: 16px;
  padding: ${spacing.xl};
  max-width: 500px;
  width: 90%;
  position: relative;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  text-align: center;
`;

const CloseButton = styled.button`
  position: absolute;
  top: ${spacing.md};
  right: ${spacing.md};
  background: transparent;
  border: none;
  color: ${color.N7};
  cursor: pointer;
  padding: ${spacing.xs};
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  transition: all 0.2s;

  &:hover {
    background: ${color.N3};
    color: ${color.N10};
  }

  svg {
    width: 20px;
    height: 20px;
  }
`;

const BadgeIconContainer = styled(motion.div)<{ $color: string }>`
  width: 120px;
  height: 120px;
  margin: 0 auto ${spacing.lg} auto;
  background: ${(props) => props.$color};
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  position: relative;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);

  svg {
    width: 64px;
    height: 64px;
  }
`;

const SparkleContainer = styled(motion.div)<{
  $top: number;
  $left: number;
  $delay: number;
}>`
  position: absolute;
  top: ${(props) => props.$top}%;
  left: ${(props) => props.$left}%;
  color: ${color.Y5};
`;

const BadgeName = styled.h2`
  font-size: 28px;
  font-weight: 700;
  color: ${color.N10};
  margin: 0 0 ${spacing.sm} 0;
`;

const BadgeDescription = styled.p`
  font-size: 16px;
  color: ${color.N7};
  line-height: 1.5;
  margin: 0 0 ${spacing.lg} 0;
`;

const AwardMessage = styled.p`
  font-size: 14px;
  color: ${color.N6};
  margin: 0 0 ${spacing.xl} 0;
  font-style: italic;
`;

const ActionButton = styled.button`
  background: ${color.B5};
  color: white;
  border: none;
  padding: ${spacing.md} ${spacing.xl};
  border-radius: 8px;
  font-size: 16px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);

  &:hover {
    background: ${color.B6};
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  &:active {
    transform: translateY(0);
  }
`;

export interface BadgeCelebrationModalProps {
  badgeName: string;
  badgeDescription: string;
  badgeIcon: string;
  badgeColor: string;
  isAutoAwarded: boolean;
  awardedBy?: {
    username: string;
  };
  onClose: () => void;
  onViewBadges?: () => void;
}

/**
 * Full-screen celebration modal for badge awards.
 * Displays badge with animation effects and sparkles.
 */
export function BadgeCelebrationModal({
  badgeName,
  badgeDescription,
  badgeIcon,
  badgeColor,
  isAutoAwarded,
  awardedBy,
  onClose,
  onViewBadges,
}: BadgeCelebrationModalProps) {
  const [showSparkles, setShowSparkles] = useState(true);

  // Get the icon component from lucide-react
  const IconComponent = (LucideIcons as any)[badgeIcon] || LucideIcons.Award;

  // Hide sparkles after animation
  useEffect(() => {
    const timer = setTimeout(() => {
      setShowSparkles(false);
    }, 2000);
    return () => clearTimeout(timer);
  }, []);

  // Sparkle positions (randomly distributed)
  const sparklePositions = [
    { top: 10, left: 20, delay: 0 },
    { top: 15, left: 80, delay: 0.1 },
    { top: 40, left: 10, delay: 0.2 },
    { top: 60, left: 85, delay: 0.15 },
    { top: 80, left: 25, delay: 0.25 },
    { top: 85, left: 75, delay: 0.05 },
  ];

  const awardMessage = isAutoAwarded
    ? "Congratulations on your achievement!"
    : `Awarded by ${awardedBy?.username || "a fellow user"}`;

  return (
    <AnimatePresence>
      <Overlay
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <ModalContainer
          initial={{ scale: 0.8, opacity: 0, y: 20 }}
          animate={{ scale: 1, opacity: 1, y: 0 }}
          exit={{ scale: 0.8, opacity: 0, y: 20 }}
          transition={{ type: "spring", damping: 20, stiffness: 300 }}
          onClick={(e) => e.stopPropagation()}
        >
          <CloseButton onClick={onClose} aria-label="Close">
            <X />
          </CloseButton>

          <BadgeIconContainer
            $color={badgeColor}
            initial={{ scale: 0, rotate: -180 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{
              type: "spring",
              damping: 15,
              stiffness: 200,
              delay: 0.2,
            }}
          >
            <IconComponent />

            {showSparkles &&
              sparklePositions.map((pos, index) => (
                <SparkleContainer
                  key={index}
                  $top={pos.top}
                  $left={pos.left}
                  $delay={pos.delay}
                  initial={{ scale: 0, opacity: 0 }}
                  animate={{
                    scale: [0, 1.2, 0],
                    opacity: [0, 1, 0],
                    rotate: [0, 180, 360],
                  }}
                  transition={{
                    duration: 1.5,
                    delay: pos.delay,
                    ease: "easeOut",
                  }}
                >
                  <Sparkles size={20} />
                </SparkleContainer>
              ))}
          </BadgeIconContainer>

          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
          >
            <BadgeName>{badgeName}</BadgeName>
            <BadgeDescription>{badgeDescription}</BadgeDescription>
            <AwardMessage>{awardMessage}</AwardMessage>

            {onViewBadges && (
              <ActionButton
                onClick={() => {
                  onViewBadges();
                  onClose();
                }}
              >
                View Your Badges
              </ActionButton>
            )}
          </motion.div>
        </ModalContainer>
      </Overlay>
    </AnimatePresence>
  );
}

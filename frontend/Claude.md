# Frontend Design Language

## Design Philosophy

The design system emphasizes clarity, depth, and delight through subtle animations and thoughtful visual hierarchy.

## Core Design Principles

### 1. Visual Hierarchy Through Depth

- **Layered Cards**: White cards on subtle gradient backgrounds create clear content separation
- **Shadow System**:
  - Base: `0 4px 6px rgba(0, 0, 0, 0.04)`
  - Hover: `0 10px 25px rgba(0, 0, 0, 0.08)`
  - Elevation creates focus and interactivity cues

### 2. Color Palette

- **Primary Gradient**: `linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%)` (Indigo to Purple)
- **Success Gradient**: `linear-gradient(135deg, #10b981 0%, #059669 100%)` (Emerald)
- **Background**: `#f5f7fa` to `#fafbfc` (Light gray gradients)
- **Text Hierarchy**:
  - Headlines: `#1e293b` (Dark slate)
  - Body: `#475569` (Medium slate)
  - Labels: `#64748b` to `#94a3b8` (Light slate)

### 3. Typography

- **Headers**: 2.25rem with -0.03em letter-spacing for tight, modern feel
- **Gradient Text**: Using `-webkit-background-clip: text` for premium feel on titles
- **Uppercase Labels**: 0.8125rem with 0.08em spacing for form fields
- **Font Weights**: 400 (regular), 600 (semi-bold), 700 (bold)

### 4. Interactive Elements

#### Buttons

```css
/* Primary button with hover state */
background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
border-radius: 12px;
padding: 0.875rem 1.5rem;
box-shadow: 0 4px 14px rgba(99, 102, 241, 0.25);

/* Hover effect with overlay */
&::before {
  /* Gradient overlay that fades in on hover */
  background: linear-gradient(135deg, #818cf8 0%, #a78bfa 100%);
  opacity: 0;
  transition: opacity 0.3s ease;
}

&:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(99, 102, 241, 0.35);
}
```

#### Form Inputs

```css
padding: 0.875rem 1rem;
border: 2px solid #cbd5e1;
border-radius: 10px;
transition: all 0.3s ease;

&:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
```

### 5. Micro-interactions

- **Transform on Hover**: `translateY(-2px)` for lift effect
- **Smooth Transitions**: `cubic-bezier(0.4, 0, 0.2, 1)` for natural motion
- **Ripple Effects**: Expanding circles on button clicks
- **Gradient Animations**: Subtle color shifts on interactive elements

### 6. Visual Accents

- **Top Bar Gradient**: Rainbow gradient `(#6366f1 → #8b5cf6 → #ec4899)` as brand accent
- **Left Border Indicators**: 3-4px gradient bars for active/hover states
- **Badge Styles**: Pill-shaped with gradient backgrounds and soft shadows
- **Flow Connectors**: Dotted gradient lines connecting related actions

### 7. Responsive Design

- **Desktop**: Full layouts with generous 2rem padding
- **Tablet** (768px): Reduced padding to 1.5rem, 2-column grids
- **Mobile** (480px): Single column, 1rem padding, stacked layouts
- **Touch Optimization**: Disabled hover transforms on touch devices

### 8. Accessibility & Contrast

- **Text Contrast**: Minimum WCAG AA compliance
  - Dark text (#1e293b) on light backgrounds
  - Light text (white) on gradient backgrounds
- **Interactive States**: Clear visual feedback for disabled states
- **Permission Indicators**: Visual + text indicators for restricted actions

## Implementation Examples

### Section Headers

```tsx
const SectionHeader = styled.div`
  padding: 1.5rem 1.75rem;
  background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%);
  border-bottom: 2px solid #e2e8f0;
`;
```

### Info Cards

```tsx
const InfoSection = styled.div`
  background: white;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.04);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  &:hover {
    transform: translateY(-1px);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.08);
  }
`;
```

### Action Cards with Flow

```tsx
const ActionFlow = styled.div`
  border-left: 2px solid transparent;
  border-image: linear-gradient(180deg, #e0e7ff, #c7d2fe, #e0e7ff) 1;

  /* Connection dots */
  &::before,
  &::after {
    width: 10px;
    height: 10px;
    background: linear-gradient(135deg, #8b5cf6, #6366f1);
    border-radius: 50%;
    box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.2);
  }
`;
```

## Design Inspiration

- **Jony Ive**: Minimalism with purposeful ornamentation
- **Dieter Rams**: "Good design is as little design as possible" - achieved through subtle gradients and clean layouts
- **Modern SaaS**: Linear, Vercel, and Stripe's use of gradients and depth
- **Material Design 3**: Elevation system and responsive layouts

## Future Enhancements

- Dark mode support with inverted gradients
- CSS variables for theme customization
- Animation sequences for complex interactions
- Glassmorphism effects for overlays

const base = {
  width: 13, height: 13, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
  "aria-hidden": true,
};

export const ClockIcon = () => (
  <svg {...base}><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></svg>
);
export const PinIcon = () => (
  <svg {...base}><path d="M12 21s-7-6.2-7-11.5A7 7 0 0 1 19 9.5C19 14.8 12 21 12 21z" /><circle cx="12" cy="9.5" r="2.5" /></svg>
);
export const PeopleIcon = () => (
  <svg {...base}><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20a6.5 6.5 0 0 1 13 0" /><path d="M16 4.5a3.5 3.5 0 0 1 0 7M21.5 20a6.5 6.5 0 0 0-4-6" /></svg>
);
export const SearchIcon = () => (
  <svg {...base} width={15} height={15}><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg>
);
export const CloseIcon = () => (
  <svg {...base} width={16} height={16}><path d="M6 6l12 12M18 6 6 18" /></svg>
);
export const MailIcon = () => (
  <svg {...base}><rect x="3" y="5" width="18" height="14" rx="2.5" /><path d="m4 7 8 6 8-6" /></svg>
);
export const CalendarIcon = () => (
  <svg {...base}><rect x="3.5" y="5" width="17" height="15" rx="2.5" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>
);
export const NoteIcon = () => (
  <svg {...base}><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5M9 13h7M9 17h5" /></svg>
);
export const LinkIcon = () => (
  <svg {...base}><path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1" /><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1" /></svg>
);
export const ListIcon = () => (
  <svg {...base}><path d="M9 6h11M9 12h11M9 18h11" /><circle cx="4.5" cy="6" r="1" /><circle cx="4.5" cy="12" r="1" /><circle cx="4.5" cy="18" r="1" /></svg>
);
export const ChatIcon = () => (
  <svg {...base}><path d="M4 5h16v11H9l-5 4z" /><path d="M8 9h8M8 12h5" /></svg>
);
export const CheckIcon = () => (
  <svg {...base} width={14} height={14} strokeWidth={2.6}><path d="m5 12.5 4.5 4.5L19 7.5" /></svg>
);
export const CheckCircleIcon = () => (
  <svg {...base}><circle cx="12" cy="12" r="9" /><path d="m8 12.5 2.7 2.7L16 9.8" /></svg>
);
export const GlobeIcon = () => (
  <svg {...base}><circle cx="12" cy="12" r="9" /><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z" /></svg>
);
export const ChevronUpIcon = () => (
  <svg {...base}><path d="M6 15l6-6 6 6" /></svg>
);
export const PhoneIcon = () => (
  <svg {...base}><rect x="7" y="3" width="10" height="18" rx="2.5" /><path d="M11 17.5h2" /></svg>
);
export const EyeOffIcon = () => (
  <svg {...base}><path d="M3 3l18 18" /><path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6 0 9.5 7 9.5 7a17 17 0 0 1-2.7 3.6M6.6 6.6A17 17 0 0 0 2.5 12s3.5 7 9.5 7a9.6 9.6 0 0 0 4.4-1.1" /><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" /></svg>
);
export const MoonIcon = () => (
  <svg {...base}><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" /></svg>
);
export const SunIcon = () => (
  <svg {...base}><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></svg>
);

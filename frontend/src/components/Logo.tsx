import { useState } from "react";
import { companyInitials } from "../format";

/** Organisation logo, or an initials tile when there is none (or it fails to load). */
export default function Logo({ src, company, size = 30 }: { src: string | null; company: string; size?: number }) {
  const [failed, setFailed] = useState(false);
  const style = { width: size, height: size };
  if (!src || failed) {
    return (
      <span className="logo logo-tile" style={{ ...style, fontSize: size * 0.36 }} aria-hidden>
        {companyInitials(company)}
      </span>
    );
  }
  return (
    <span className="logo" style={style}>
      <img src={src} alt={`${company} logo`} loading="lazy" referrerPolicy="no-referrer" onError={() => setFailed(true)} />
    </span>
  );
}

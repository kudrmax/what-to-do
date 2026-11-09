import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useChangeSettings, useCities } from "../api/hooks";
import { Icon, type IconName } from "./Icon";
import "./AppShell.css";

const SECTIONS: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: "Ближайшие", icon: "sun" },
  { to: "/calendar", label: "Календарь", icon: "calendar" },
  { to: "/plans", label: "Собираюсь пойти", icon: "bookmark" },
  { to: "/sources", label: "Источники", icon: "feed" },
];

export function AppShell({ children, activeSection }: { children: ReactNode; activeSection?: string }) {
  return (
    <div className="shell">
      <nav className="shell__nav" aria-label="Разделы">
        <CityMenu />
        {SECTIONS.map((section) => (
          <NavLink
            key={section.to}
            to={section.to}
            end
            className={({ isActive }) => `shell__link${isActive || activeSection === section.to ? " shell__link--active" : ""}`}
          >
            <Icon name={section.icon} />
            {section.label}
          </NavLink>
        ))}
      </nav>
      <main className="shell__main">{children}</main>
    </div>
  );
}

function CityMenu() {
  const cities = useCities();
  const changeSettings = useChangeSettings();
  const [open, setOpen] = useState(false);
  const menu = useRef<HTMLDivElement>(null);
  const active = cities.data?.find((city) => city.active);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!menu.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  return (
    <div className="city" ref={menu}>
      <button type="button" className="city__button" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <Icon name="pin" className="city__pin" />
        <span className="city__name">{active?.name ?? "Город не выбран"}</span>
        <Icon name="chevronDown" size={16} className="city__chevron" />
      </button>
      {open && (
        <div className="city__menu" role="menu">
          {cities.data?.map((city) => (
            <button
              key={city.id}
              type="button"
              role="menuitemradio"
              aria-checked={city.active}
              className="city__option"
              onClick={() => {
                if (!city.active) changeSettings.mutate({ active_city_id: city.id });
                setOpen(false);
              }}
            >
              {city.name}
              {city.active && <Icon name="check" size={16} />}
            </button>
          ))}
          <NavLink to="/sources" className="city__add" onClick={() => setOpen(false)}>
            <Icon name="plus" size={16} />
            Добавить город
          </NavLink>
        </div>
      )}
    </div>
  );
}

import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import { useChangeSettings, useCities } from "../api/queries";
import { useActiveCity } from "../api/useActiveCity";
import { Icon } from "../ui/Icon";
import { Popover } from "../ui/Popover";
import { SECTIONS } from "./routes";
import "./AppShell.css";

const MENU = [SECTIONS.feed, SECTIONS.calendar, SECTIONS.plans, SECTIONS.sources];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="shell">
      <nav className="shell__nav" aria-label="Разделы">
        <CityMenu />
        {MENU.map((section) => (
          <NavLink key={section.path} to={section.path} end className="shell__link">
            <Icon name={section.icon} />
            {section.title}
          </NavLink>
        ))}
        <NavLink to={SECTIONS.settings.path} className="shell__link shell__link--bottom">
          <Icon name={SECTIONS.settings.icon} />
          {SECTIONS.settings.title}
        </NavLink>
      </nav>
      <main className="shell__main">{children}</main>
    </div>
  );
}

function CityMenu() {
  const cities = useCities();
  const { city } = useActiveCity();
  const change = useChangeSettings();
  return (
    <Popover
      className="city"
      trigger={(open, toggle) => (
        <button type="button" className="city__button" aria-haspopup="menu" aria-expanded={open} onClick={toggle}>
          <Icon name="pin" className="city__pin" />
          <span className="city__name">{city?.name ?? "Город не выбран"}</span>
          <Icon name="chevronDown" size={16} className="city__chevron" />
        </button>
      )}
    >
      {(close) => (
        <>
          {cities.data?.map((option) => (
            <button
              key={option.id}
              type="button"
              role="menuitemradio"
              aria-checked={option.id === city?.id}
              className="popover__item city__option"
              onClick={() => {
                if (option.id !== city?.id) change.mutate({ active_city_id: option.id });
                close();
              }}
            >
              <span>{option.name}</span>
              {option.id === city?.id && <Icon name="check" size={16} />}
            </button>
          ))}
          <div className="popover__footer">
            <NavLink to={SECTIONS.settings.path} className="popover__item" onClick={close}>
              <Icon name="plus" size={16} />
              Добавить город
            </NavLink>
          </div>
        </>
      )}
    </Popover>
  );
}

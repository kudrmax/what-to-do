import type { ReactNode } from "react";

import { Icon, type IconName } from "../ui/Icon";
import "./Onboarding.css";

/** What a newcomer needs to find the first sources of a city they may not know the channels of. */
export function FindingSources({ city }: { city: string }) {
  return (
    <section className="finding" aria-labelledby="finding-title">
      <h2 id="finding-title" className="finding__title">
        How to find sources
      </h2>
      <ol className="finding__steps">
        <Step icon="search" title="Search Telegram">
          Try <span className="finding__query">{city} events</span> or <span className="finding__query">{city} afisha</span>, and look at channels of venues, clubs and communities you know.
        </Step>
        <Step icon="eye" title="Check that it is public">
          Open <span className="finding__query">t.me/s/name</span> in a browser, with the channel’s name. If its posts show there, the app can read it.
        </Step>
        <Step icon="instagram" title="Instagram profiles too">
          Paste <span className="finding__query">instagram.com/name</span> of a venue or a community. Only public profiles work.
        </Step>
        <Step icon="globe" title="Websites work too">
          Paste a link to any event page of a site with event listings: the app finds the site’s other events by itself.
        </Step>
      </ol>
      <p className="finding__next">
        <Icon name="refresh" size={15} />
        Add a few above, then click Refresh in Upcoming.
      </p>
    </section>
  );
}

function Step({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  return (
    <li className="finding__step">
      <span className="finding__icon">
        <Icon name={icon} size={18} />
      </span>
      <div className="finding__body">
        <h3 className="finding__step-title">{title}</h3>
        <p className="finding__text">{children}</p>
      </div>
    </li>
  );
}

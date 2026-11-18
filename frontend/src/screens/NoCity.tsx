import { useActiveCity } from "../api/useActiveCity";
import { Icon } from "../ui/Icon";
import { NewCity } from "./CitiesSection";
import "./Onboarding.css";

/** The first thing a new app asks: the city, right where the feed will be. */
export function NoCity() {
  const { loading } = useActiveCity();
  if (loading) return null;
  return (
    <section className="welcome" aria-labelledby="welcome-title">
      <div className="welcome__intro">
        <span className="welcome__icon">
          <Icon name="pin" size={22} />
        </span>
        <h2 id="welcome-title" className="welcome__title">
          Where are you looking for things to do?
        </h2>
        <p className="welcome__text">Add your city. Then add Telegram channels, Instagram profiles and websites that announce events there, and Claude turns their posts into event cards.</p>
      </div>
      <NewCity canCancel={false} />
    </section>
  );
}

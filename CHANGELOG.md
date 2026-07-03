# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

- Initial scaffold: login/session handling for PWEB (Amano Korea) portals and
  a single placeholder sensor. Dashboard field parsing not yet implemented.
- Added discount-registration status and balance sensors, a discount-history
  calendar, a vehicle-exit event entity, and a `register_discount` action
  service, based on the 할인등록/할인등록현황/할인권구매(통합) screens.
- Reworked the config flow into 3 steps: enter the numeric iLotArea, confirm
  the site name fetched from the (unauthenticated) `/login` page, then enter
  ID/password.

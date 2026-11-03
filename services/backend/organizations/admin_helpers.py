def full_name(user):
    profile = getattr(user, "organization_profile", None)
    return (profile.full_name if profile and profile.full_name else user.get_full_name()) or "—"


def department_name(user, organization_id=None):
    memberships = [membership for membership in user.organization_memberships.all()
                   if membership.department and (organization_id is None or membership.organization_id == organization_id)]
    if organization_id is not None or len(memberships) <= 1:
        return "; ".join(dict.fromkeys(membership.department for membership in memberships)) or "—"
    return "; ".join(f"{membership.organization.name}: {membership.department}" for membership in memberships)

# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def migrate(cr, version):
    """Force every existing pack to the hidden default Pack Display Type.

    ``pack_type`` became cosmetic and hidden (see CLAUDE.md), defaulted to
    ``non_detailed`` on create only. Records created before that keep whatever
    they had, which still drives OCA's ``pack_component_price`` visibility and
    reads as an inconsistent database.
    """
    # ponytail: plain SQL, no ORM. pack_type is a stored Selection column with
    # no compute, inverse or constraint, so nothing needs to fire on write.
    cr.execute(
        """
        UPDATE product_template
           SET pack_type = 'non_detailed'
         WHERE pack_ok IS TRUE
           AND pack_type IS DISTINCT FROM 'non_detailed'
        """
    )

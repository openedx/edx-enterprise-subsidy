"""
Tests for functionality provided in the ``models.py`` module.
"""
from itertools import product
from unittest import mock
from uuid import uuid4

import ddt
from django.test import TestCase
from openedx_ledger.models import TransactionStateChoices
from openedx_ledger.test_utils.factories import (
    ExternalFulfillmentProviderFactory,
    ExternalTransactionReferenceFactory,
    TransactionFactory
)
from requests.exceptions import HTTPError
from rest_framework import status

from test_utils.utils import MockResponse

from ..models import ContentNotFoundForCustomerException
from .factories import SubsidyFactory


@ddt.ddt
class SubsidyModelReadTestCase(TestCase):
    """
    Tests functionality defined in the ``Subsidy`` model.
    """
    @classmethod
    def setUpTestData(cls):
        """
        We assume that tests in this class don't mutate self.subsidy,
        or if they do, take care to reset/clean-up the subsidy state
        at the end of the test.  This allows us to use setUpTestData(),
        which runs only once before every test in this TestCase is run.
        """
        cls.enterprise_customer_uuid = uuid4()
        cls.subsidy = SubsidyFactory.create(
            enterprise_customer_uuid=cls.enterprise_customer_uuid,
        )
        cls.subsidy.catalog_client = mock.MagicMock()
        super().setUpTestData()

    def setUp(self):
        super().setUp()
        # Clear the method cache between tests to help make tests deterministic.
        self.subsidy.price_for_content.cache_clear()

    def test_price_for_content(self):
        """
        Tests that Subsidy.price_for_content returns the price of a piece
        of content from the catalog client converted to cents of a dollar.
        """
        content_price_cents = 19998

        self.subsidy.catalog_client.get_course_price.return_value = content_price_cents

        actual_price_cents = self.subsidy.price_for_content('some-content-key')
        self.assertEqual(actual_price_cents, content_price_cents)
        self.subsidy.catalog_client.get_course_price.assert_called_once_with(
            self.enterprise_customer_uuid,
            'some-content-key',
        )

    def test_price_for_content_not_in_catalog(self):
        """
        Tests that Subsidy.price_for_content raises ContentNotFoundForCustomerException
        if the content is not part of any catalog for the customer.
        """
        self.subsidy.catalog_client.get_course_price.side_effect = HTTPError(
            response=MockResponse(None, status.HTTP_404_NOT_FOUND),
        )

        with self.assertRaises(ContentNotFoundForCustomerException):
            self.subsidy.price_for_content('some-content-key')

    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @ddt.data(True, False)
    def test_is_redeemable(self, expected_to_be_redeemable, mock_price_for_content):
        """
        Tests that Subsidy.is_redeemable() returns true when the subsidy
        has enough remaining balance to cover the price of the given content,
        and false otherwise.
        """
        # Mock the content price to be slightly too expensive if
        # expected_to_be_redeemable is false;
        # mock it to be slightly affordable if true.
        constant = -100 if expected_to_be_redeemable else 100
        content_price = self.subsidy.current_balance() + constant
        mock_price_for_content.return_value = content_price

        is_redeemable, actual_content_price = self.subsidy.is_redeemable('some-content-key')

        self.assertEqual(is_redeemable, expected_to_be_redeemable)
        self.assertEqual(content_price, actual_content_price)


class SubsidyModelRedemptionTestCase(TestCase):
    """
    Tests functionality related to redemption on the Subsidy model
    """
    def setUp(self):
        self.enterprise_customer_uuid = uuid4()
        self.subsidy_access_policy_uuid = uuid4()
        self.subsidy = SubsidyFactory.create(
            enterprise_customer_uuid=self.enterprise_customer_uuid,
        )
        super().setUp()

    def test_get_redemption(self):
        """
        Tests that get_redemption appropriately filters by learner and content identifiers.
        """
        alice_learner_id, bob_learner_id = (23, 42)
        learner_content_pairs = list(product(
            (alice_learner_id, bob_learner_id),
            ('science-content-key', 'art-content-key'),
        ))
        for learner_id, content_key in learner_content_pairs:
            TransactionFactory.create(
                state=TransactionStateChoices.COMMITTED,
                quantity=-1000,
                ledger=self.subsidy.ledger,
                lms_user_id=learner_id,
                content_key=content_key
            )

        for learner_id, content_key in learner_content_pairs:
            transaction = self.subsidy.get_redemption(learner_id, content_key)
            self.assertEqual(transaction.lms_user_id, learner_id)
            self.assertEqual(transaction.content_key, content_key)
            self.assertEqual(transaction.quantity, -1000)
            self.assertEqual(transaction.state, TransactionStateChoices.COMMITTED)

    def test_commit_transaction(self):
        """
        Tests that commit_transaction creates a transaction with the correct state.
        """
        transaction = TransactionFactory.create(
            state=TransactionStateChoices.PENDING,
            ledger=self.subsidy.ledger,
        )
        fulfillment_identifier = 'some-fulfillment-identifier'
        provider = ExternalFulfillmentProviderFactory()
        external_reference = ExternalTransactionReferenceFactory(
            external_fulfillment_provider=provider,
        )
        self.subsidy.commit_transaction(
            ledger_transaction=transaction,
            fulfillment_identifier=fulfillment_identifier,
            external_reference=external_reference,
        )
        transaction.refresh_from_db()
        self.assertEqual(
            transaction.external_reference.first(),
            external_reference
        )
        self.assertEqual(
            transaction.external_reference.first().external_fulfillment_provider,
            provider
        )

    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.price_for_content')
    @mock.patch('enterprise_subsidy.apps.subsidy.models.Subsidy.enterprise_client')
    def test_redeem_not_existing(self, mock_enterprise_client, mock_price_for_content):
        """
        Test Subsidy.redeem() happy path (i.e. the redemption/transaction does not already exist, and calling redeem()
        creates one).
        """
        learner_id = 1
        content_key = "course-v1:edX+test+course"
        subsidy_access_policy_uuid = str(uuid4())
        mock_enterprise_fulfillment_uuid = str(uuid4())
        mock_content_price = 1000
        mock_price_for_content.return_value = mock_content_price
        mock_enterprise_client.enroll.return_value = mock_enterprise_fulfillment_uuid
        new_transaction, transaction_created = self.subsidy.redeem(learner_id, content_key, subsidy_access_policy_uuid)
        assert transaction_created
        assert new_transaction.state == TransactionStateChoices.COMMITTED
        assert new_transaction.quantity == -mock_content_price

import Purchases, {
  INTRO_ELIGIBILITY_STATUS,
  PACKAGE_TYPE,
  LOG_LEVEL,
  PURCHASES_ERROR_CODE,
} from 'react-native-purchases';
import { Platform } from 'react-native';
import Constants from 'expo-constants';

// Revenue Cat API keys from environment variables
const REVENUE_CAT_API_KEY_IOS = process.env.EXPO_PUBLIC_REVENUE_CAT_API_KEY_IOS || 'your_ios_api_key_here';

const REVENUE_CAT_API_KEY_ANDROID = process.env.EXPO_PUBLIC_REVENUE_CAT_API_KEY_ANDROID || 'your_android_api_key_here';

// Subscription product identifiers (these will be configured in Revenue Cat dashboard)
export const PRODUCT_IDS = {
  MONTHLY: 'recipe_wizard_monthly',
  YEARLY: 'recipe_wizard_yearly',
} as const;

// Entitlement identifier (this determines what features the user has access to)
export const ENTITLEMENT_ID = process.env.EXPO_PUBLIC_REVENUE_CAT_ENTITLEMENT_ID || 'premium_features';

export interface PurchaseInfo {
  isActive: boolean;
  productId: string | null;
  originalPurchaseDate: string | null;
  expirationDate: string | null;
  willRenew: boolean;
  isInIntroOfferPeriod: boolean;
  isInGracePeriod: boolean;
}

export interface OfferingInfo {
  identifier: string;
  serverDescription: string;
  packages: Array<{
    identifier: string;
    packageType: PACKAGE_TYPE;
    originalPackage: any; // Store the original Package object for purchases
    product: {
      identifier: string;
      description: string;
      title: string;
      price: string;
      priceString: string;
      currencyCode: string;
      introPrice?: {
        price: string;
        priceString: string;
        period: string;
        cycles: number;
      };
    };
  }>;
}

export interface TransactionInfo {
  id: string;
  date: string;
  amountDisplay: string; // currency-safe display string
  amountValue: number | null; // numeric value for totals when currency known
  currencyCode?: string;
  plan: string;
  period: string;
  status: 'completed' | 'pending' | 'failed' | 'refunded';
  paymentMethod: string;
  description: string;
  receiptUrl?: string;
}

class PurchasesService {
  private isInitialized = false;
  private pendingUserId: string | null = null;

  async initialize(userId?: string): Promise<void> {
    try {
      // Check if running in Expo Go (Revenue Cat doesn't work in Expo Go)
      const isExpoGo = Constants.appOwnership === 'expo';

      if (isExpoGo) {
        if (__DEV__) { /* console.log('🔧 Expo Go detected - Revenue Cat disabled, using mock mode'); */ }
        this.isInitialized = true;
        return;
      }

      // Configure Revenue Cat with appropriate API key for platform
      const apiKey = Platform.OS === 'ios' ? REVENUE_CAT_API_KEY_IOS : REVENUE_CAT_API_KEY_ANDROID;

      // Validate API key format for current platform
      const missingIos = Platform.OS === 'ios' && (!apiKey || apiKey === 'your_ios_api_key_here');
      const missingAndroid = Platform.OS === 'android' && (!apiKey || apiKey === 'your_android_api_key_here');
      if (missingIos || missingAndroid) {
        throw new Error('Revenue Cat API key not configured for this platform');
      }


      // Set appropriate log level for production
      Purchases.setLogLevel(__DEV__ ? LOG_LEVEL.INFO : LOG_LEVEL.WARN);

      // Initialize Revenue Cat
      await Purchases.configure({ apiKey });

      // Set user ID if provided (for analytics and support)
      if (userId) {
        await Purchases.logIn(userId);
      }

      this.isInitialized = true;
      // console.log('✅ Revenue Cat initialized successfully');

      // Apply any identification request that arrived before the SDK was ready
      if (this.pendingUserId) {
        const id = this.pendingUserId;
        this.pendingUserId = null;
        await this.setUserID(id);
      }
    } catch (error) {
      console.error('❌ Failed to initialize Revenue Cat:', error);
      throw new Error('Failed to initialize purchase service');
    }
  }

  async getCurrentCustomerInfo(): Promise<any> {
    if (!this.isInitialized) {
      throw new Error('Purchases service not initialized');
    }

    try {
      // console.log('📞 Making RevenueCat API call: getCustomerInfo()');
      const customerInfo = await Purchases.getCustomerInfo();
      // console.log('✅ getCustomerInfo() success:', {
      //   originalAppUserId: customerInfo.originalAppUserId,
      //   activeEntitlements: Object.keys(customerInfo.entitlements.active),
      //   allEntitlements: Object.keys(customerInfo.entitlements.all),
      //   requestDate: customerInfo.requestDate
      // });
      return customerInfo;
    } catch (error: any) {
      console.error('❌ getCustomerInfo() failed:', {
        error: error.message,
        code: error.code,
        underlyingError: error.underlyingErrorMessage,
        fullError: error
      });
      throw error;
    }
  }

  async getPremiumStatus(): Promise<PurchaseInfo> {
    try {
      const customerInfo = await this.getCurrentCustomerInfo();
      const entitlement = customerInfo.entitlements.active[ENTITLEMENT_ID];

      if (entitlement) {
        return {
          isActive: true,
          productId: entitlement.productIdentifier,
          originalPurchaseDate: entitlement.originalPurchaseDate,
          expirationDate: entitlement.expirationDate,
          willRenew: entitlement.willRenew,
          isInIntroOfferPeriod: Boolean((entitlement as any).isInIntroOfferPeriod),
          isInGracePeriod: Boolean((entitlement as any).isInGracePeriod),
        };
      }

      return {
        isActive: false,
        productId: null,
        originalPurchaseDate: null,
        expirationDate: null,
        willRenew: false,
        isInIntroOfferPeriod: false,
        isInGracePeriod: false,
      };
    } catch (error) {
      console.error('❌ Failed to get premium status:', error);
      // Return inactive status on error to be safe
      return {
        isActive: false,
        productId: null,
        originalPurchaseDate: null,
        expirationDate: null,
        willRenew: false,
        isInIntroOfferPeriod: false,
        isInGracePeriod: false,
      };
    }
  }

  async getOfferings(): Promise<OfferingInfo[]> {
    if (!this.isInitialized) {
      throw new Error('Purchases service not initialized');
    }

    try {
      // console.log('📞 Making RevenueCat API call: getOfferings()');
      const offerings = await Purchases.getOfferings();

      // console.log('✅ getOfferings() raw response:', {
      //   currentOfferingId: offerings.current?.identifier,
      //   allOfferingsCount: Object.keys(offerings.all).length,
      //   allOfferingIds: Object.keys(offerings.all),
      //   fullResponse: offerings
      // });

      // Ensure current offering (if present) is first for deterministic selection
      const allOfferings = Object.values((offerings as any).all || {});
      const current = (offerings as any).current ? [(offerings as any).current] : [];
      const others = allOfferings.filter((o: any) => !(offerings as any).current || o.identifier !== (offerings as any).current.identifier);
      const ordered = [...current, ...others];

      const processedOfferings = ordered.map((offering: any) => {
        // console.log(`📦 Processing offering: ${offering.identifier}`, {
        //   description: offering.serverDescription,
        //   packagesCount: offering.availablePackages.length,
        //   packageIds: offering.availablePackages.map(p => p.identifier)
        // });

        return {
          identifier: offering.identifier,
          serverDescription: offering.serverDescription,
          packages: offering.availablePackages.map((pkg: any) => {
            // console.log(`📦 Processing package: ${pkg.identifier}`, {
            //   productId: pkg.product.identifier,
            //   price: pkg.product.priceString,
            //   title: pkg.product.title
            // });

            return {
              identifier: pkg.identifier,
              packageType: pkg.packageType,
              originalPackage: pkg, // Store the original Package object
              product: {
                identifier: pkg.product.identifier,
                description: pkg.product.description,
                title: pkg.product.title,
                price: pkg.product.price.toString(),
                priceString: pkg.product.priceString,
                currencyCode: pkg.product.currencyCode,
                introPrice: pkg.product.introPrice ? {
                  price: pkg.product.introPrice.price.toString(),
                  priceString: pkg.product.introPrice.priceString,
                  period: pkg.product.introPrice.period,
                  cycles: pkg.product.introPrice.cycles,
                } : undefined,
              },
            };
          }),
        };
      });

      // console.log('✅ getOfferings() processed:', processedOfferings);
      return processedOfferings;
    } catch (error: any) {
      console.error('❌ getOfferings() failed:', {
        error: error.message,
        code: error.code,
        underlyingError: error.underlyingErrorMessage,
        fullError: error
      });
      throw error;
    }
  }

  async purchasePackage(packageToPurchase: any): Promise<any> {
    if (!this.isInitialized) {
      throw new Error('Purchases service not initialized');
    }

    try {
      // console.log('🛒 Starting purchase process for:', packageToPurchase.product.identifier);

      if (!packageToPurchase || !(packageToPurchase as any).identifier) {
        throw new Error('Invalid purchase package');
      }

      const { customerInfo } = await Purchases.purchasePackage(packageToPurchase);

      // console.log('✅ Purchase completed successfully');
      return customerInfo;
    } catch (error) {
      console.error('❌ Purchase failed:', error);

      // Robust error handling without instanceof (PurchasesError is a type, not a class)
      const err: any = error || {};
      const code = err.code;

      if (err.userCancelled || code === PURCHASES_ERROR_CODE.PURCHASE_CANCELLED_ERROR) {
        throw new Error('Purchase was cancelled');
      }
      switch (code) {
        case PURCHASES_ERROR_CODE.PAYMENT_PENDING_ERROR:
          throw new Error('Payment is pending');
        case PURCHASES_ERROR_CODE.PRODUCT_NOT_AVAILABLE_FOR_PURCHASE_ERROR:
          throw new Error('Product not available for purchase');
        case PURCHASES_ERROR_CODE.STORE_PROBLEM_ERROR:
          throw new Error('Store connection problem');
        default:
          throw new Error(`Purchase failed: ${err.message || String(err)}`);
      }
    }
  }

  async purchasePackageWithUpgrade(packageToPurchase: any, currentProductId?: string | null): Promise<any> {
    if (!this.isInitialized) {
      throw new Error('Purchases service not initialized');
    }
    try {
      if (!packageToPurchase || !(packageToPurchase as any).identifier) {
        throw new Error('Invalid purchase package');
      }
      let customerInfo: any;
      if (Platform.OS === 'android' && currentProductId) {
        // Use oldSKU as expected by some SDK typings
        ({ customerInfo } = await Purchases.purchasePackage(packageToPurchase, { oldSKU: currentProductId } as any));
      } else {
        ({ customerInfo } = await Purchases.purchasePackage(packageToPurchase));
      }
      return customerInfo;
    } catch (error) {
      console.error('❌ Purchase (upgrade) failed:', error);
      throw error;
    }
  }

  async restorePurchases(): Promise<any> {
    if (!this.isInitialized) {
      throw new Error('Purchases service not initialized');
    }

    try {
      // console.log('🔄 Restoring purchases...');

      const customerInfo = await Purchases.restorePurchases();

      // console.log('✅ Purchases restored successfully');
      return customerInfo;
    } catch (error) {
      console.error('❌ Failed to restore purchases:', error);
      throw error;
    }
  }

  async checkTrialEligibility(productIds: string[]): Promise<Record<string, INTRO_ELIGIBILITY_STATUS>> {
    if (!this.isInitialized) {
      throw new Error('Purchases service not initialized');
    }

    try {
      const eligibility = await ((Purchases as any).checkTrialOrIntroductoryPriceEligibility?.(productIds) ?? {});
      return eligibility;
    } catch (error) {
      console.error('❌ Failed to check trial eligibility:', error);
      throw error;
    }
  }

  async setUserID(userId: string): Promise<void> {
    if (!this.isInitialized) {
      // SDK isn't ready yet (e.g. AuthContext's session-restore raced ahead of
      // PremiumContext's SDK init) — queue it and let `initialize()` apply it
      // once the SDK comes up, instead of dropping the identification.
      this.pendingUserId = userId;
      // console.log('⏳ Purchases service not yet initialized, queuing user ID:', userId);
      return;
    }

    if (this.isMockMode) {
      return;
    }

    try {
      await Purchases.logIn(userId);
      // console.log('✅ User ID set successfully:', userId);
    } catch (error) {
      console.error('❌ Failed to set user ID:', error);
      throw error;
    }
  }

  async logout(): Promise<void> {
    if (!this.isInitialized) {
      return;
    }

    try {
      await Purchases.logOut();
      // console.log('✅ User logged out successfully');
    } catch (error) {
      console.error('❌ Failed to logout:', error);
      throw error;
    }
  }

  async getProductInfo(productId: string): Promise<{ planName: string; price: string; period: string } | null> {
    try {
      const offerings = await this.getOfferings();

      // Search through all offerings for the product
      for (const offering of offerings) {
        for (const pkg of offering.packages) {
          if (pkg.product.identifier === productId) {
            let planName = 'Premium Subscription';
            let period = 'month';

            // Use exact product ID matching
            if (productId === PRODUCT_IDS.MONTHLY) {
              planName = 'Monthly Premium';
              period = 'month';
            } else if (productId === PRODUCT_IDS.YEARLY) {
              planName = 'Yearly Premium';
              period = 'year';
            }

            return {
              planName,
              price: pkg.product.priceString, // Real price from Revenue Cat
              period,
            };
          }
        }
      }

      // Fallback if product not found in offerings
      let planName = 'Premium Subscription';
      let price = 'N/A';
      let period = 'month';

      if (productId === PRODUCT_IDS.MONTHLY) {
        planName = 'Monthly Premium';
        price = '$4.99'; // Fallback price
        period = 'month';
      } else if (productId === PRODUCT_IDS.YEARLY) {
        planName = 'Yearly Premium';
        price = '$49.99'; // Fallback price
        period = 'year';
      }

      return { planName, price, period };
    } catch (error) {
      console.error('❌ Failed to get product info:', error);
      return null;
    }
  }

  async getTransactionHistory(): Promise<TransactionInfo[]> {
    try {
      const customerInfo = await this.getCurrentCustomerInfo();
      const transactions: TransactionInfo[] = [];

      // Build product pricing lookup from current offerings for currency-safe display
      let productPricing: Record<string, { priceNumber: number; priceString: string; currencyCode: string; period: string; planName: string } > = {};
      try {
        const offs = await this.getOfferings();
        offs.forEach(off => off.packages.forEach(pkg => {
          const isMonthly = pkg.packageType === PACKAGE_TYPE.MONTHLY;
          const isYearly = pkg.packageType === PACKAGE_TYPE.ANNUAL;
          const period = isMonthly ? 'month' : (isYearly ? 'year' : 'period');
          productPricing[pkg.product.identifier] = {
            priceNumber: Number(pkg.product.price),
            priceString: pkg.product.priceString,
            currencyCode: pkg.product.currencyCode,
            period,
            planName: pkg.product.title || (isMonthly ? 'Monthly Premium' : isYearly ? 'Yearly Premium' : 'Premium Subscription'),
          };
        }));
      } catch {}

      // Get all entitlements (active and expired)
      const allEntitlements: any[] = Object.values(((customerInfo as any)?.entitlements?.all) || {});

      for (let index = 0; index < allEntitlements.length; index++) {
        const entitlement: any = allEntitlements[index];

        if (entitlement.originalPurchaseDate && entitlement.productIdentifier) {
          const pricing = productPricing[entitlement.productIdentifier];
          const planName = pricing?.planName || 'Premium Subscription';
          const period = pricing?.period || 'month';
          const amountDisplay = pricing?.priceString || '—';
          const amountValue = typeof pricing?.priceNumber === 'number' && !isNaN(pricing.priceNumber) ? pricing.priceNumber : null;
          const currencyCode = pricing?.currencyCode;

          // Determine status based on entitlement state
          let status: TransactionInfo['status'] = 'completed';
          if (entitlement.isActive) {
            status = 'completed';
          } else if (entitlement.expirationDate && new Date(entitlement.expirationDate) < new Date()) {
            status = 'completed'; // Expired but was successful
          }

          // Generate unique transaction ID
          const purchaseTimestamp = new Date(entitlement.originalPurchaseDate).getTime();
          const transactionId = `RC${purchaseTimestamp.toString().slice(-10)}${entitlement.productIdentifier.slice(-4)}`;

          transactions.push({
            id: transactionId,
            date: entitlement.originalPurchaseDate,
            amountDisplay,
            amountValue,
            currencyCode,
            plan: planName,
            period,
            status,
            paymentMethod: (customerInfo as any)?.managementURL?.includes('play.google.com') ? 'Google Play' : 'App Store',
            description: `${planName} Subscription`,
          });
        }
      }

      // Include non-subscription transactions when available
      const nst = (customerInfo as any)?.nonSubscriptionTransactions as Array<any> | undefined;
      if (Array.isArray(nst)) {
        nst.forEach((t) => {
          const date = t?.purchaseDate || t?.transactionDate || new Date().toISOString();
          const id = t?.transactionIdentifier || t?.id || `TXN${Math.random().toString(36).slice(2, 10).toUpperCase()}`;
          const productId = t?.productIdentifier;
          const pricing = productId ? productPricing[productId] : undefined;
          transactions.push({
            id,
            date,
            amountDisplay: pricing?.priceString || '—',
            amountValue: typeof pricing?.priceNumber === 'number' && !isNaN(pricing.priceNumber) ? pricing.priceNumber : null,
            currencyCode: pricing?.currencyCode,
            plan: pricing?.planName || (productId || 'One-time Purchase'),
            period: pricing?.period || '—',
            status: 'completed',
            paymentMethod: t?.store === 'play_store' ? 'Google Play' : 'App Store',
            description: `${pricing?.planName || 'In-App Purchase'}`,
          });
        });
      }

      // Sort by date (most recent first)
      return transactions.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    } catch (error) {
      console.error('❌ Failed to get transaction history:', error);
      throw error;
    }
  }

  // Mock implementation for testing when API keys are not set up
  async getMockPremiumStatus(): Promise<PurchaseInfo> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 1000));

    // In development, return a mock status based on environment
    const isDevelopment = __DEV__ && (process.env.EXPO_PUBLIC_IS_PREMIUM === 'true');

    return {
      isActive: isDevelopment,
      productId: isDevelopment ? PRODUCT_IDS.MONTHLY : null,
      originalPurchaseDate: isDevelopment ? new Date().toISOString() : null,
      expirationDate: isDevelopment ? new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString() : null,
      willRenew: isDevelopment,
      isInIntroOfferPeriod: false,
      isInGracePeriod: false,
    };
  }

  async getMockOfferings(): Promise<OfferingInfo[]> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 500));

    return [
      {
        identifier: 'default',
        serverDescription: 'Recipe Wizard Premium Plans',
        packages: [
          {
            identifier: PRODUCT_IDS.MONTHLY,
            packageType: PACKAGE_TYPE.MONTHLY,
            originalPackage: {} as any, // Mock package for development
            product: {
              identifier: PRODUCT_IDS.MONTHLY,
              description: 'Premium features including unlimited recipe generation and smart shopping lists',
              title: 'Recipe Wizard Premium Monthly',
              price: '4.99',
              priceString: '$4.99',
              currencyCode: 'USD',
              introPrice: {
                price: '0.99',
                priceString: '$0.99',
                period: 'P1W',
                cycles: 1,
              },
            },
          },
          {
            identifier: PRODUCT_IDS.YEARLY,
            packageType: PACKAGE_TYPE.ANNUAL,
            originalPackage: {} as any, // Mock package for development
            product: {
              identifier: PRODUCT_IDS.YEARLY,
              description: 'Premium features including unlimited recipe generation and smart shopping lists',
              title: 'Recipe Wizard Premium Yearly',
              price: '49.99',
              priceString: '$49.99',
              currencyCode: 'USD',
              introPrice: {
                price: '9.99',
                priceString: '$9.99',
                period: 'P1M',
                cycles: 1,
              },
            },
          },
        ],
      },
    ];
  }

  async getMockTransactionHistory(): Promise<TransactionInfo[]> {
    // Simulate network delay
    await new Promise(resolve => setTimeout(resolve, 800));

    const transactions: TransactionInfo[] = [];
    const now = new Date();

    // Generate 3-5 mock transactions
    const numTransactions = Math.floor(Math.random() * 3) + 3;
    for (let i = 0; i < numTransactions; i++) {
      const transactionDate = new Date(now.getTime() - (i * 30 * 24 * 60 * 60 * 1000));
      const plans = ['Monthly Premium', 'Yearly Premium'];
      const amounts = ['$4.99', '$49.99'];
      const periods = ['month', 'year'];

      const planIndex = Math.floor(Math.random() * plans.length);
      const plan = plans[planIndex];
      const amount = amounts[planIndex];
      const period = periods[planIndex];

      transactions.push({
        id: 'TXN' + Math.random().toString(36).substr(2, 8).toUpperCase(),
        date: transactionDate.toISOString(),
        amountDisplay: amount,
        amountValue: parseFloat(amount.replace('$', '')),
        currencyCode: 'USD',
        plan,
        period,
        status: 'completed',
        paymentMethod: 'App Store',
        description: `${plan} Subscription`,
      });
    }

    return transactions.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
  }

  // Check if we're using mock data (before real API keys are set up or in Expo Go)
  get isMockMode(): boolean {
    const isExpoGo = Constants.appOwnership === 'expo';
    const hasIosKey = REVENUE_CAT_API_KEY_IOS && REVENUE_CAT_API_KEY_IOS !== 'your_ios_api_key_here' && REVENUE_CAT_API_KEY_IOS !== 'INSERT_KEY_HERE' && REVENUE_CAT_API_KEY_IOS.startsWith('appl_');
    const hasAndroidKey = REVENUE_CAT_API_KEY_ANDROID && REVENUE_CAT_API_KEY_ANDROID !== 'your_android_api_key_here' && REVENUE_CAT_API_KEY_ANDROID !== 'INSERT_KEY_HERE' && REVENUE_CAT_API_KEY_ANDROID.startsWith('goog_');
    const hasKeyForPlatform = Platform.OS === 'ios' ? hasIosKey : hasAndroidKey;
    return isExpoGo || !hasKeyForPlatform;
  }

  async getManagementURL(): Promise<string | null> {
    try {
      const url = await (Purchases as any).getManagementURL?.();
      return url || null;
    } catch {
      return null;
    }
  }
}

// Export singleton instance
export const purchasesService = new PurchasesService();

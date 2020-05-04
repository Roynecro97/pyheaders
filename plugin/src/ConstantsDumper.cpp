#include "clang/AST/AST.h"
#include "clang/AST/ASTConsumer.h"
#include "clang/AST/RecursiveASTVisitor.h"
#include "clang/Frontend/CompilerInstance.h"
#include "clang/Frontend/FrontendPluginRegistry.h"

#include <cctype>
#include <cstdio>
#include <iomanip>
#include <iostream>
#include <string>
#include <string_view>
#include <tuple>

using namespace std;
using namespace clang;

#if __cplusplus < 201402L
using llvm::make_unique;
#endif

// #define DEBUG_PLUGIN
#ifndef DEBUG_PLUGIN
#define DBG(...)
#define DBG_NOTE(...)
#else
#define DBG(expr)                                                      \
    do                                                                 \
    {                                                                  \
        cerr << "\033[33m" #expr ": "                                  \
             << boolalpha << (expr) << boolalpha << "\033[0m" << endl; \
    } while (false)
// ]]

#define DBG_NOTE(expr)                              \
    do                                              \
    {                                               \
        cerr << "\033[32m" #expr "\033[0m" << endl; \
    } while (false)
// ]]
#endif // DEBUG_PLUGIN

namespace
{
//                      val, delim
using CharInfo = tuple<char, char>;
//                          value,          type                context         last
using StructInfo = tuple<const APValue &, const QualType &, const ASTContext &, bool>;
//                          value,          type                context
using ValueInfo = tuple<const APValue &, const QualType &, const ASTContext &>;

inline constexpr auto char_delim = '\'';
inline constexpr auto string_delim = '"';
inline constexpr auto escape_char = '\\';

ostream &operator<<(ostream &os, const ValueInfo &value_info);

ostream &operator<<(ostream &os, const CharInfo &char_info)
{
    constexpr auto dig_mask = 0b111;
    constexpr auto get_dig = [](auto val, auto dig_idx) constexpr
    {
        return (val >> (dig_idx * 3)) & dig_mask;
    };

    const auto [value, delim] = char_info;

    if (!isprint(static_cast<unsigned char>(value)))
    {
        os << escape_char;
        for (auto i = 3; i > 0; --i)
        {
            os << get_dig(value, i - 1);
        }
        return os;
    }

    if (value == delim)
    {
        os << escape_char;
    }
    return os << value;
}

ostream &operator<<(ostream &os, const StructInfo &struct_info)
{
    auto &&[value, type, ast_context, last] = struct_info;
    auto *record_decl = type->getAsCXXRecordDecl();

    const auto base_count = value.getStructNumBases();
    const auto field_count = value.getStructNumFields();

    auto base_iter = record_decl->bases_begin();
    auto base_end = record_decl->bases_end();
    for (unsigned i = 0; i < base_count; ++i)
    {
        const auto &base = value.getStructBase(i);

        // The amount of bases in the type should be the same as the one in the value
        // so we shouldn't get into trouble here...
        if (base_iter != base_end)
        {
            const auto &base_type = base_iter->getType();
            os << StructInfo(base, base_type, ast_context,
                             i == base_count - 1 && field_count == 0 && last);
            ++base_iter;
        }
        else
        {
            // No point to continue atm.
            break;
        }
    }

    auto field_iter = record_decl->field_begin();
    auto field_end = record_decl->field_end();
    for (unsigned i = 0; i < field_count; ++i)
    {
        const auto &field = value.getStructField(i);

        // The amount of fields in the type should be the same as the one in the value
        // so we shouldn't get into trouble here...
        if (field_iter != field_end)
        {
            const auto &field_type = field_iter->getType();
            os << ValueInfo(field, field_type, ast_context);
            if (!last || i < field_count - 1)
            {
                os << ",";
            }
            ++field_iter;
        }
        else
        {
            // No point to continue atm.
            break;
        }
    }
    return os;
}

ostream &operator<<(ostream &os, const ValueInfo &value_info)
{
    auto &&[value, type, ast_context] = value_info;

    // Print only literal types
    if (!type->isLiteralType(ast_context))
    {
        return os << "<non-literal>";
    }

    if (type->isFundamentalType())
    {
        if (type->isAnyCharacterType())
        {
            if (type->isCharType())
            {
                // Check that type is not a typedef to make uint8_t print as a number but char as a character.
                // (type == type.getCanonicalType()) // returns false on `char` for some reason
                if (type.getCanonicalType().getAsString() == type.getAsString())
                {
                    return os << char_delim << CharInfo(static_cast<char>(value.getInt().getExtValue()), char_delim) << char_delim;
                }
            }
            if (type->isWideCharType())
            {
                return os << "wchar_t(" << value.getAsString(ast_context, type) << ")";
            }
            if (type->isChar8Type())
            {
                return os << "char8_t(" << value.getAsString(ast_context, type) << ")";
            }
            if (type->isChar16Type())
            {
                return os << "char16_t(" << value.getAsString(ast_context, type) << ")";
            }
            if (type->isChar32Type())
            {
                return os << "char32_t(" << value.getAsString(ast_context, type) << ")";
            }
        }
    }
    else
    {
        if (type->isPointerType() && type->getPointeeOrArrayElementType()->isAnyCharacterType())
        {
            const auto str = value.getAsString(ast_context, type);
            // content includes the delimiters
            const auto content_begin = str.find(string_delim);
            const auto content_end = str.rfind(string_delim) + 1;
            return os << str.substr(content_begin, content_end - content_begin);
        }
        if (type->isArrayType())
        {
            const auto array_size = [](const APValue &value, const QualType &type) {
                const auto real_size = value.getArraySize();
                if (type->getPointeeOrArrayElementType()->isAnyCharacterType() && value.getArrayInitializedElt(real_size - 1).getInt() == 0)
                {
                    return real_size - 1;
                }
                return real_size;
            }(value, type); // structured binding cannot be captured
            const auto element_type = QualType(type->getPointeeOrArrayElementType(), Qualifiers::Const);

            // Handle char, signed char, unsigned char (regular strings)
            if (type->getPointeeOrArrayElementType()->isCharType())
            {
                os << string_delim;
                for (unsigned i = 0; i < array_size; ++i)
                {
                    os << CharInfo(static_cast<char>(value.getArrayInitializedElt(i).getInt().getExtValue()), string_delim);
                }
                return os << string_delim;
            }
            // Handle wchar_t, char8_t, char16_t, char32_t (special encoding strings)
            if (type->getPointeeOrArrayElementType()->isAnyCharacterType())
            {
                os << element_type.getCanonicalType().getUnqualifiedType().getAsString() << "[]";
            }

            os << "(";
            for (unsigned i = 0; i < array_size; ++i)
            {
                os << ValueInfo(value.getArrayInitializedElt(i), element_type, ast_context);
                if (i < array_size - 1)
                {
                    os << ",";
                }
            }
            return os << ")";
        }
        if (type->isRecordType() && value.isStruct())
        {
            auto class_name = type.getCanonicalType().getUnqualifiedType().getAsString();
            // Actual name starts after "struct " or "class "
            const auto actual_begin = class_name.find(' ') + 1;
            return os << class_name.substr(actual_begin, class_name.size() - actual_begin)
                      << "(" << StructInfo(value, type, ast_context, true) << ")";
        }
    }

    // Default for all types that don't require special handling (ie: most `int`s, `float`, ...)
    return os << value.getAsString(ast_context, type);
}

class ConstantsDumperClassVisitor : public RecursiveASTVisitor<ConstantsDumperClassVisitor>
{
public:
    bool VisitEnumDecl(EnumDecl *decl)
    {
        DBG_NOTE(---------------------);
        DBG_NOTE(Enter VisitEnumDecl());

        DBG(decl->getNameAsString());          // bar
        DBG(decl->getQualifiedNameAsString()); // foo::bar
        DBG(decl->getIntegerType().getAsString());

        cout << "enum " << decl->getQualifiedNameAsString() << " {" << endl;
        for (auto &&enum_constant_decl : decl->enumerators())
        {
            cout << enum_constant_decl->getQualifiedNameAsString() << "="
                 << ValueInfo(APValue(enum_constant_decl->getInitVal()), decl->getIntegerType(), decl->getASTContext())
                 << "," << endl;
        }
        cout << "}" << endl;

        DBG_NOTE(Leave VisitEnumDecl());
        DBG_NOTE(---------------------);

        return true;
    }

    bool VisitVarDecl(VarDecl *decl)
    {
        DBG_NOTE(--------------------);
        DBG_NOTE(Enter VisitVarDecl());

        DBG(decl->getNameAsString());                                               // bar
        DBG(decl->getQualifiedNameAsString());                                      // foo::bar
        DBG(decl->getType().getQualifiers().getAsString());                         // const
        DBG(decl->getType().getCanonicalType().getUnqualifiedType().getAsString()); // int
        DBG(decl->getType().getCanonicalType().getAsString());                      // const int
        DBG(decl->getType().getUnqualifiedType().getAsString());                    // int32_t
        DBG(decl->getType().getAsString());                                         // const int32_t
        DBG(decl->getType()->isFundamentalType());
        DBG(decl->getType()->isRecordType());
        DBG(decl->getType()->isLiteralType(decl->getASTContext()));
        DBG(decl->getType()->isArrayType());
        DBG(decl->getType()->isConstantArrayType());
        DBG(decl->getType()->isPointerType());

#ifdef DEBUG_PLUGIN
        if (decl->getType()->isArrayType() || decl->getType()->isPointerType())
        {
            DBG(QualType(decl->getType()->getPointeeOrArrayElementType(), Qualifiers::Const).getAsString());
        }

        if (decl->getType()->isRecordType())
        {
            auto *recordDecl = decl->getType()->getAsCXXRecordDecl();
            DBG(recordDecl->isPOD());
            DBG(recordDecl->isStandardLayout());
            DBG(recordDecl->isCXX11StandardLayout());
            DBG(recordDecl->isLiteral());
            DBG(decl->getType()->getAsRecordDecl()->getBody());
            DBG(decl->getType()->getAsRecordDecl()->getNameAsString());

            DBG(recordDecl->getNameAsString());
            DBG(recordDecl->getQualifiedNameAsString());
            // cout << decl->getType().getUnqualifiedType().getAsString();
            // if (!recordDecl->bases().empty())
            // {
            //     cout << " :";
            //     for (auto &&base : recordDecl->bases())
            //     {
            //         cout << " " << base.getType().getAsString() << ",";
            //     }
            // }
            // cout << " {" << endl;
            // for (auto *fieldDecl : recordDecl->fields())
            // {
            //     cout << fieldDecl->getNameAsString() << ": " << fieldDecl->getType().getUnqualifiedType().getAsString() << "," << endl;
            // }
            // cout << "}" << endl;
        }
        if (decl->getEvaluatedValue())
        {
            DBG(decl->getEvaluatedValue()->getAsString(decl->getASTContext(), decl->getType()));
        }
#endif // DEBUG_PLUGIN

        // Check only literal types
        if (!decl->getType()->isLiteralType(decl->getASTContext()))
        {
            DBG_NOTE(Leave VisitVarDecl()[not literal]);
            DBG_NOTE(--------------------);

            return true;
        }

        // Exclude function parameters
        if (decl->isLocalVarDeclOrParm() && !decl->isLocalVarDecl())
        {
            DBG_NOTE(Leave VisitVarDecl()[local parameter]);
            DBG_NOTE(--------------------);

            return true;
        }

        // Make sure there is an initialization for the variable
        if (!decl->hasInit())
        {
            DBG_NOTE(Leave VisitVarDecl()[no init]);
            DBG_NOTE(--------------------);

            return true;
        }

        if (decl->isConstexpr() || (decl->checkInitIsICE() && decl->isUsableInConstantExpressions(decl->getASTContext())))
        {
            if (decl->getEvaluatedValue() == nullptr)
            {
                DBG_NOTE(Leave VisitVarDecl()[no value]);
                DBG_NOTE(--------------------);

                return true;
            }

#ifdef DEBUG_PLUGIN
            if (decl->getType()->isAnyCharacterType())
            {
                DBG(decl->getType()->isCharType());
                DBG(decl->getType()->isWideCharType());
                DBG(decl->getType()->isChar8Type());
                DBG(decl->getType()->isChar16Type());
                DBG(decl->getType()->isChar32Type());
            }
            if (decl->getEvaluatedValue()->isInt())
            {
                DBG(decl->getEvaluatedValue()->getInt().getExtValue());
                DBG(decl->getEvaluatedValue()->getInt().getSExtValue());
                DBG(decl->getEvaluatedValue()->getInt().getZExtValue());
            }
            if (decl->getEvaluatedValue()->isFloat())
            {
                DBG(decl->getEvaluatedValue()->getFloat().convertToFloat());
                DBG(decl->getEvaluatedValue()->getFloat().convertToDouble());
            }
            if (decl->getEvaluatedValue()->isStruct())
            {
                for (unsigned base_index = 0; base_index < decl->getEvaluatedValue()->getStructNumBases(); ++base_index)
                {
                    DBG(base_index);
                    auto base = decl->getEvaluatedValue()->getStructBase(base_index);

                    for (unsigned base_field_index = 0; base_field_index < base.getStructNumFields(); ++base_field_index)
                    {
                        DBG(base_field_index);
                        auto base_field = base.getStructField(base_field_index);
                        DBG(base_field.getAsString(decl->getASTContext(), decl->getType()));
                    }
                    // DBG(base.getAsString(decl->getASTContext(), decl->getType()));
                }
                for (unsigned field_index = 0; field_index < decl->getEvaluatedValue()->getStructNumFields(); ++field_index)
                {
                    DBG(field_index);
                    auto field = decl->getEvaluatedValue()->getStructField(field_index);
                    DBG(field.getAsString(decl->getASTContext(), decl->getType()));
                }
            }
#endif // DEBUG_PLUGIN

            cout << decl->getQualifiedNameAsString() << "="
                 << ValueInfo(*decl->getEvaluatedValue(), decl->getType(), decl->getASTContext()) << endl;
        }

        DBG_NOTE(Leave VisitVarDecl());
        DBG_NOTE(--------------------);
        return true;
    }
};

class ConstantsDumperConsumer : public ASTConsumer
{
public:
    void HandleTranslationUnit(ASTContext &context)
    {
        visitor.TraverseDecl(context.getTranslationUnitDecl());
    }

private:
    ConstantsDumperClassVisitor visitor;
};

class ConstantsDumperASTAction : public PluginASTAction
{
public:
    virtual unique_ptr<ASTConsumer> CreateASTConsumer(CompilerInstance &Compiler, llvm::StringRef InFile)
    {
        return make_unique<ConstantsDumperConsumer>();
    }

    bool ParseArgs(const CompilerInstance &CI,
                   const vector<string> &args)
    {
        return true;
    }
};
} // namespace

static clang::FrontendPluginRegistry::Add<ConstantsDumperASTAction> X("ConstantsDumper", "Dumps all constants and enums from the code");
